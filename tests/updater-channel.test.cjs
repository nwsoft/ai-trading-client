const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { GitHubProvider } = require('../webui/node_modules/electron-updater/out/providers/GitHubProvider.js');
const { displayVersion } = require('../webui/electron/version.cjs');
const { updateErrorMessage } = require('../webui/electron/update-errors.cjs');

const source = fs.readFileSync(path.join(__dirname, '../webui/electron/main.cjs'), 'utf8');
const allowPrerelease = /autoUpdater\.allowPrerelease = (true|false);/.exec(source)[1] === 'true';
const feed = `<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>
<title>v3.9.0.10</title><link href="https://github.com/nwsoft/ai-trading-client/releases/tag/v3.9.0.10"/>
<content>retired single EXE</content></entry></feed>`;
const metadata = `version: 3.9.136
files:
  - url: NoahAI-3.9.1.36-Setup.exe
    sha512: fixture-sha512
path: NoahAI-3.9.1.36-Setup.exe
sha512: fixture-sha512
`;

function provider(prerelease, missingMetadata = false) {
  const requested = [];
  const updater = { allowPrerelease: prerelease, currentVersion: '3.9.136', channel: null, fullChangelog: false };
  const executor = { request: async options => {
    requested.push(options.path);
    if (options.path.endsWith('/releases.atom')) return feed;
    if (options.path.endsWith('/releases/latest')) return JSON.stringify({ tag_name: 'v3.9.1.36' });
    if (options.path.endsWith('/v3.9.1.36/latest.yml') && !missingMetadata) return metadata;
    throw new Error('fixture missing metadata: ' + options.path);
  } };
  return { client: new GitHubProvider({ owner: 'nwsoft', repo: 'ai-trading-client' }, updater, { executor, platform: 'win32' }), requested };
}

test('reproduces legacy Atom selection under old prerelease policy', async () => {
  const { client, requested } = provider(true);
  await assert.rejects(client.getLatestVersion(), /v3\.9\.0\.10\/latest.yml/);
  assert.ok(!requested.some(p => p.endsWith('/releases/latest')));
});

test('installed updater selects stable latest despite stale Atom feed', async () => {
  assert.equal(allowPrerelease, false);
  assert.match(source, /autoUpdater\.allowDowngrade = false/);
  const { client, requested } = provider(allowPrerelease);
  const info = await client.getLatestVersion();
  assert.equal(info.tag, 'v3.9.1.36');
  assert.equal(displayVersion(info), '3.9.1.36');
  assert.equal(client.resolveFiles(info)[0].url.pathname, '/nwsoft/ai-trading-client/releases/download/v3.9.1.36/NoahAI-3.9.1.36-Setup.exe');
  assert.ok(requested.some(p => p.endsWith('/releases/latest')));
  assert.ok(!requested.some(p => p.includes('/v3.9.0.10/')));
});

test('missing stable metadata fails closed without falling back to legacy release', async () => {
  const { client, requested } = provider(allowPrerelease, true);
  await assert.rejects(client.getLatestVersion(), /v3\.9\.1\.36\/latest.yml/);
  assert.ok(!requested.some(p => p.includes('/v3.9.0.10/')));
});

test('404 explanation does not expose stack/headers or ask for a user token', () => {
  const message = updateErrorMessage({ code: 'ERR_UPDATER_CHANNEL_FILE_NOT_FOUND', message: 'Cannot find latest.yml Headers: SECRET at C:\\Program Files' });
  assert.match(message, /배포 채널/);
  assert.match(message, /토큰 문제로 판단하지 않습니다/);
  assert.doesNotMatch(message, /SECRET|Headers|Program Files/);
  assert.match(updateErrorMessage({ code: 'ERR_UPDATER_INVALID_SIGNATURE' }), /설치를 중단/);
});
