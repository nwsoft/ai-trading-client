function updateErrorMessage(error) {
  const code = String(error?.code || "");
  const message = String(error?.message || error || "");
  if (code === "ERR_UPDATER_CHANNEL_FILE_NOT_FOUND" || /Cannot find latest(?:-mac)?\.yml/.test(message)) {
    return "공개 릴리스의 자동업데이트 파일을 찾지 못했습니다. 배포 채널·파일 구성을 확인해야 하는 오류이며, 이 메시지만으로 사용자 인증 토큰 문제로 판단하지 않습니다. ‘최신 릴리스 열기’에서 공식 설치본을 확인하세요. 현재 앱과 거래 엔진은 종료하지 않았습니다.";
  }
  if (/sha512|checksum|ERR_UPDATER_INVALID_SIGNATURE|ERR_UPDATER_CHECKSUM_MISMATCH/i.test(code + message)) {
    return "업데이트 파일의 무결성 또는 서명을 확인하지 못해 설치를 중단했습니다. 다시 다운로드하거나 공식 배포 상태를 확인하세요.";
  }
  // Do not put HTTP headers, internal paths and library stack traces into UI.
  return "업데이트 확인 또는 다운로드에 실패했습니다. 네트워크와 공식 배포 상태를 확인한 뒤 다시 시도하세요. 현재 앱은 그대로 사용할 수 있습니다.";
}

module.exports = { updateErrorMessage };
