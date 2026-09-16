const { build } = require("./package.json");
const signed = process.env.NOAHAI_MAC_SIGNED === "1";
module.exports = {
  ...build,
  directories: { output: "../deploy/mac-release" },
  extraResources: [{ from: "../deploy/mac-engine", to: "engine", filter: ["noahai-engine"] }],
  forceCodeSigning: signed,
  mac: {
    ...build.mac,
    target: [{ target: "dmg", arch: ["arm64"] }, { target: "zip", arch: ["arm64"] }],
    artifactName: "NoahAI-" + build.buildVersion + "-arm64.${ext}",
    identity: signed ? process.env.CSC_NAME : null,
    hardenedRuntime: signed,
    notarize: signed,
  },
};
