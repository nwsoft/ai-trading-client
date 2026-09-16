function productVersion(updaterVersion) {
  const match = String(updaterVersion || "").match(/^(\d+)\.(\d+)\.(\d+)$/);
  if (!match) return String(updaterVersion || "");
  const encoded = Number(match[3]);
  if (!Number.isInteger(encoded) || encoded < 100) return String(updaterVersion || "");
  return `${match[1]}.${match[2]}.${Math.floor(encoded / 100)}.${encoded % 100}`;
}

function packageProductVersion(packageInfo, runtimeVersion) {
  const buildVersion = String(packageInfo?.build?.buildVersion || "").trim();
  if (/^\d+\.\d+\.\d+\.\d+$/.test(buildVersion)) return buildVersion;
  const packageVersion = productVersion(packageInfo?.version);
  if (/^\d+\.\d+\.\d+\.\d+$/.test(packageVersion)) return packageVersion;
  return productVersion(runtimeVersion);
}

function displayVersion(info) {
  // latest.yml is the updater contract. A stale/cached GitHub releaseName
  // from the retired single-EXE channel must never override its version.
  const metadataVersion = productVersion(info?.version);
  if (/^\d+\.\d+\.\d+\.\d+$/.test(metadataVersion)) return metadataVersion;
  const releaseName = String(info?.releaseName || "").trim();
  const productMatch = releaseName.match(/v?(\d+\.\d+\.\d+\.\d+)/i);
  return productMatch?.[1] || metadataVersion;
}

module.exports = { displayVersion, packageProductVersion, productVersion };
