import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from backend.app.config import settings
from backend.app.schemas import AuditRequest, AuditAccepted, AuditJob, Health
from backend.app.services.audit_service import run_audit
from backend.app.services.url_safety import resolve_public, UnsafeURL
from backend.app.storage import AuditStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = AuditStore(settings.database_path)
    app.state.store.recover_interrupted()
    app.state.jobs = {}
    app.state.tasks = set()
    yield
    for task in app.state.tasks:
        task.cancel()
    await asyncio.gather(*app.state.tasks, return_exceptions=True)


app = FastAPI(title='Crawlens SEO Audit API', version='1.2.0', description='Evidence-based SEO scoring, SQLite audit history, and OpenAI-compatible recommendations. Single-worker local workspace.', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(','), allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])


@app.middleware('http')
async def guard_requests(request: Request, call_next):
    # Reject large inputs before JSON parsing and cross-origin browser submissions.
    if request.method == 'POST':
        origin = request.headers.get('origin')
        allowed = settings.cors_origins.split(',') + [str(request.base_url).rstrip('/')]
        if origin and origin not in allowed:
            return JSONResponse(status_code=403, content={'detail': 'This origin is not allowed.'})
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 8192:
                return JSONResponse(status_code=413, content={'detail': 'Request body is too large.'})
        request._body = bytes(body)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/api/health', response_model=Health, tags=['Service'])
async def health():
    return Health(crawler_configured=bool(settings.firecrawl_api_key), ai_configured=bool(settings.openai_api_key), pagespeed_configured=bool(settings.pagespeed_api_key),
                  model=settings.openai_model, page_limit=settings.crawl_page_limit, link_limit=settings.link_check_limit)


@app.post('/api/audits', status_code=202, response_model=AuditAccepted, tags=['Audits'])
async def start_audit(body: AuditRequest, request: Request):
    try:
        url, _ = await resolve_public(body.url)
    except UnsafeURL as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    jobs = request.app.state.jobs
    active = [job for job in jobs.values() if job.status in ('queued', 'running')]
    if any(job.website == url for job in active):
        raise HTTPException(status_code=409, detail='This website already has an audit running. Wait for it to finish.')
    if len(active) >= settings.max_concurrent_audits:
        raise HTTPException(status_code=429, detail='All audit slots are busy. Please try again shortly.', headers={'Retry-After': '15'})
    for key in list(jobs):
        if len(jobs) < settings.max_stored_audits:
            break
        if jobs[key].status in ('completed', 'failed'):
            del jobs[key]
    audit_id = f'audit_{uuid4().hex}'
    job = AuditJob(audit_id=audit_id, website=url)
    jobs[audit_id] = job
    await asyncio.to_thread(request.app.state.store.save, job)
    task = asyncio.create_task(persisted_audit(job, request.app.state.store))
    request.app.state.tasks.add(task)
    task.add_done_callback(request.app.state.tasks.discard)
    return AuditAccepted(audit_id=audit_id)


async def persisted_audit(job, store):
    worker = asyncio.create_task(run_audit(job, settings))
    try:
        while not worker.done():
            await asyncio.wait({worker}, timeout=1)
            await asyncio.to_thread(store.save, job.model_copy(deep=True))
        await worker
    except asyncio.CancelledError:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        if job.status in ('queued', 'running'):
            job.status, job.stage, job.error = 'failed', 'interrupted', 'Audit interrupted by server shutdown. Start a new audit.'
        raise
    except Exception:
        job.status, job.stage, job.error = 'failed', 'failed', 'The audit could not finish. Any saved evidence is retained.'
    finally:
        await asyncio.to_thread(store.save, job.model_copy(deep=True))


@app.get('/api/audits', tags=['Audits'])
async def audit_history(request: Request, q: str = Query(default='', max_length=200), limit: int = Query(default=20, ge=1, le=50), offset: int = Query(default=0, ge=0)):
    return await asyncio.to_thread(request.app.state.store.list, q, limit, offset)


@app.get('/api/audits/{audit_id}', response_model=AuditJob, tags=['Audits'])
async def get_audit(audit_id: str, request: Request):
    job = request.app.state.jobs.get(audit_id) or await asyncio.to_thread(request.app.state.store.get, audit_id)
    if job is None:
        raise HTTPException(status_code=404, detail='Audit not found in this workspace.')
    return job


# A production build can be served by the same process; API routes remain first.
dist = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if dist.is_dir():
    app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @app.get('/{path:path}', include_in_schema=False)
    async def frontend(path: str):
        if path.startswith('api/'):
            raise HTTPException(status_code=404, detail='Endpoint not found.')
        candidate = (dist / path).resolve()
        if candidate.is_relative_to(dist.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / 'index.html')
