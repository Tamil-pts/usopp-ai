import {existsSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const cwd = fileURLToPath(new URL('../nami/', import.meta.url));
const installOnly = process.argv.includes('--install-only');
function npm(args) {
  // cmd is required for npm.cmd on Windows; arguments are fixed build commands.
  const result = process.platform === 'win32'
    ? spawnSync('cmd.exe', ['/d', '/s', '/c', 'npm ' + args.join(' ')], {cwd, stdio: 'inherit'})
    : spawnSync('npm', args, {cwd, stdio: 'inherit'});
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
// The root TypeScript build imports Nami's metadata parser and therefore needs
// Nami's dependencies (including xlsx) before it can compile the main app.
if (installOnly || !existsSync(new URL('../nami/node_modules/.package-lock.json', import.meta.url))) {
  npm(['ci', '--no-audit', '--no-fund']);
}
if (!installOnly) npm(['run', 'build']);
