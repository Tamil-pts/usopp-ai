"""Run a local Project Intelligence worker against the existing data volume."""
import argparse
import os
import signal
import threading


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kinds',default='',help='Comma-separated job kinds; empty accepts all kinds.')
    parser.add_argument('--healthcheck',action='store_true',help='Check a recent persistent worker heartbeat.')
    args=parser.parse_args()
    os.environ['USOPP_PI_WORKER_MODE']='external'
    from . import jobs,store
    if args.healthcheck:
        import time,socket
        from backend.core.workhub import store as hub
        store.initialize()
        with hub.db() as db:row=db.execute('SELECT MAX(heartbeat) FROM pi_worker_health WHERE id LIKE ?',(socket.gethostname()+':%',)).fetchone()
        raise SystemExit(0 if row and row[0] and time.time()-row[0]<45 else 1)
    kinds={value.strip() for value in args.kinds.split(',') if value.strip()}
    if kinds-jobs.KINDS:parser.error('Unsupported worker job kind.')
    stop=threading.Event()
    for name in ('SIGINT','SIGTERM'):
        if hasattr(signal,name):signal.signal(getattr(signal,name),lambda *_:stop.set())
    store.initialize()
    # Stop the isolated child on shutdown; unfinished work is safely requeued.
    jobs.run(stop,kinds or None)


if __name__=='__main__':main()
