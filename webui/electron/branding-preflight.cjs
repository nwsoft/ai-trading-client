const { spawnSync } = require('node:child_process');
const path = require('node:path');

module.exports = async function brandingPreflight(context) {
  const root = path.resolve(context.packager.projectDir, '..');
  const python = process.env.NOAHAI_BUILD_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  const result = spawnSync(python, [path.join(root, 'scripts/verify_branding.py'), '--root', root], {
    cwd: root, stdio: 'inherit',
  });
  if (result.error || result.status !== 0) {
    throw new Error('NoahAI branding preflight failed: ' + (result.error || result.status));
  }
};
