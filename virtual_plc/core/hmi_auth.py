"""Bounded source-password startup using the original virtual PLC scheduler."""
import time
from .hmi_runtime import password_source_status


def prepare_password_sources(runtime,model,control,advance,refresh=False,password=None):
    status=password_source_status(model,control,runtime)
    if not status['waitingLevels'] and not refresh and runtime._initialized:return status
    if refresh and not status['producers']:return status
    if status['waitingLevels'] and not status['producers']:raise ValueError('Password snippets are empty and no assigned source writer was found. Review the login program task assignment.')
    if not runtime.run_allowed:raise ValueError('Password initialization needs supported PLC startup. Review How to run or open the source login preview.')
    if runtime.status=='faulted':raise ValueError('Reset the PLC source fault before initializing password snippets.')
    if runtime._pending is not None:raise ValueError('Finish the paused source scan or reset before initializing password snippets.')
    original=runtime.status;started=runtime.time_ms;deadline=time.monotonic()+30
    task_ids={row['taskId'] for row in status['producers'] if not refresh or 'cyclic' in row['phases']}
    if not task_ids and runtime._initialized:return status
    counts={task['id']:task['executionCount'] for task in runtime.tasks if task['id'] in task_ids}
    first_due=min((task['nextDueMs'] for task in runtime.tasks if task['id'] in task_ids and task.get('nextDueMs') is not None),default=started)
    next_check=started if not runtime._initialized else first_due
    completed=False
    runtime.command('run',return_snapshot=False)
    try:
        for _ in range(25000):
            if runtime.time_ms-started>10000 or time.monotonic()>deadline:break
            advance()
            if runtime.status!='running':break  # Preserve faults, breakpoints and source-requested stops.
            if runtime.time_ms+1e-8>=next_check:
                status=password_source_status(model,control,runtime)
                refreshed=not refresh or all(task['executionCount']>counts[task['id']] for task in runtime.tasks if task['id'] in counts)
                if refresh:
                    completed=refreshed
                elif password is not None:
                    from .hmi_runtime import password_needs_initialization
                    completed=not password_needs_initialization(model,control,runtime,password)
                else:completed=not status['waitingLevels']
                if completed:break
                next_check=min((task['nextDueMs'] for task in runtime.tasks if task['id'] in task_ids and task.get('nextDueMs') is not None),default=runtime.time_ms+10)
        status=password_source_status(model,control,runtime)
        runtime._event('hmi-initialization','Scheduled PLC password source startup',advancedMs=runtime.time_ms-started,
                       configuredLevels=status.get('configuredLevels',[]),readyLevels=status['readyLevels'])
        if runtime.status=='faulted':raise ValueError('PLC startup stopped at a source fault before the password sources were ready. Review the execution trace.')
        if not completed:
            reason='A source breakpoint or stop paused initialization.' if runtime.status!='running' else 'The bounded initialization period ended.'
            message=' The login display update is pending; continue its scheduled PLC tasks.' if refresh else ' Password sources remain uninitialized; continue their scheduled PLC tasks before retrying.'
            raise ValueError(reason+message)
        return status
    finally:
        if original!='running' and runtime.status=='running':runtime.command('pause',return_snapshot=False)
