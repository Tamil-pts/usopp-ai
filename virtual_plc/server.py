"""Mount Virtual PLC and the existing application in the same server."""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import os
from pathlib import Path


def create_app():
    from backend.app import app
    from backend.core.runtime import RESOURCE_ROOT
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles
    from virtual_plc.api import router, service

    if getattr(app.state, 'virtual_plc_installed', False):
        return app
    before = list(app.router.routes)
    spa_route = next((route for route in before if getattr(route, 'path', None) == '/{path:path}'), None)
    app.include_router(router)

    @app.get('/virtual-plc/navigation.js', include_in_schema=False)
    def navigation_script():
        return FileResponse(Path(__file__).parent / 'navigation.js', media_type='text/javascript',
                            headers={'Cache-Control': 'no-store'})

    distribution = Path(__file__).parent / 'dist'
    if distribution.is_dir():
        app.mount('/virtual-plc', StaticFiles(directory=distribution, html=True), name='virtual-plc')

    @app.get('/', include_in_schema=False)
    def application_home():
        page = RESOURCE_ROOT / 'dist/index.html'
        if not page.is_file():
            return HTMLResponse('<h1>uSOPp.ai</h1><p>Build the main interface, or <a href="/virtual-plc/">open Virtual PLC</a>.</p>')
        html = page.read_text(encoding='utf-8')
        # Additive navigation attaches after the authenticated React shell
        # mounts. The original source, index and compiled assets stay untouched.
        entry = ('<script defer src="/virtual-plc/navigation.js"></script>'
                 '<noscript><a href="/virtual-plc/" aria-label="Open Virtual PLC workspace">'
                 'Virtual PLC</a></noscript>')
        return HTMLResponse(html.replace('</body>', entry + '</body>'), headers={'Cache-Control': 'no-store'})

    @app.get('/{virtual_path:path}', include_in_schema=False)
    def application_path(virtual_path: str):
        if spa_route is None:
            from fastapi import HTTPException
            raise HTTPException(404, 'Application page not found.')
        response = spa_route.endpoint(virtual_path)
        if (isinstance(response, FileResponse) and
                Path(response.path).resolve() == (RESOURCE_ROOT / 'dist/index.html').resolve()):
            return application_home()
        return response

    # Register the extension before the existing SPA fallback. Keep all original
    # routes and their middleware, account checks, dependencies and handlers.
    added = [route for route in app.router.routes if route not in before]
    originals = [route for route in app.router.routes if route not in added]
    fallback = next((index for index, route in enumerate(originals) if getattr(route, 'path', None) == '/{path:path}'), len(originals))
    app.router.routes[:] = originals[:fallback] + added + originals[fallback:]
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            try:
                yield
            finally:
                service.close()

    app.router.lifespan_context = lifespan
    app.state.virtual_plc_installed = True
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description='uSOPp.ai with the additive Virtual PLC workspace')
    parser.add_argument('--host', default=os.getenv('USOPP_API_HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.getenv('USOPP_API_PORT', '8200')))
    args = parser.parse_args(argv)
    if not 8200 <= args.port <= 8500:
        parser.error('Choose an application port between 8200 and 8500.')
    os.environ['USOPP_API_PORT'] = str(args.port)
    os.environ['USOPP_NO_BROWSER'] = '1'
    import uvicorn
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level='info', workers=1)


if __name__ == '__main__':
    main()
