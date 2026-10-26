"""Isolated execution entrypoint requiring a supervisor-issued live lease."""
import sys
from . import jobs,store,reliability
from .resources import CURRENT_JOB
from backend.core.workhub import store as hub


def run(key,lease):
    if sys.platform=='linux':
        import resource
        from .resources import setting
        maximum=setting('MAX_OUTPUT_MB',256)*1024*1024
        resource.setrlimit(resource.RLIMIT_FSIZE,(maximum,maximum))
        resource.setrlimit(resource.RLIMIT_NOFILE,(512,512))
    store.initialize()
    with hub.db() as db:row=db.execute("SELECT * FROM pi_jobs WHERE id=? AND lease_owner=? AND status='running'",(key,lease)).fetchone()
    if not row:raise PermissionError('No active worker lease.')
    job=jobs.Job(row,lease);token=CURRENT_JOB.set(job)
    try:
        job.check()
        from backend.core import accounts
        user=next((u for u in accounts.store.list_users() if u['id']==job.row['created_by'] and u.get('active') and u.get('approved') and not u.get('isDemo')),None)
        if not user:raise PermissionError('The submitting account is no longer enabled.')
        with hub.db() as db:store.project(db,job.row['project_id'],user,write=job.row['kind'] not in {'export','q_export'})
        from .processing import process
        result=process(job,user);job.check();jobs.finish(job,'completed',result)
    except InterruptedError as error:jobs.finish(job,'cancelled',error=str(error),code='cancelled')
    except Exception as error:
        from .local_ai import ServiceUnavailable,ModelOutputError
        service=isinstance(error,ServiceUnavailable)
        invalid=isinstance(error,(ValueError,PermissionError)) and not isinstance(error,ModelOutputError) or isinstance(error,jobs.HTTPException) and error.status_code<500
        if invalid or isinstance(error,ModelOutputError):
            # Structurally valid JSON can still fail the engineering schema or
            # citation checks. Never pin that response in the reusable cache.
            with hub.db(True) as db:
                for cache_key in getattr(job,'llm_cache_keys',set()):db.execute('DELETE FROM pi_cache WHERE project_id=? AND cache_key=? AND processor=?',(job.row['project_id'],cache_key,'llm-json-v1'))
        code='source_changed' if isinstance(error,reliability.SourceChanged) else 'service_unavailable' if service else 'invalid_model_output' if isinstance(error,ModelOutputError) else 'invalid_input' if invalid else 'processing_error'
        jobs.finish(job,'blocked' if service else 'failed',error=str(getattr(error,'detail',error)),code=code,retryable=not invalid)
        from backend.core.runtime import log
        log.warning('WORKHUB_JOB_FAILED job=%s kind=%s code=%s exception=%s',key,job.row['kind'],code,type(error).__name__)
    finally:CURRENT_JOB.reset(token)


if __name__=='__main__':run(*sys.argv[1:3])
