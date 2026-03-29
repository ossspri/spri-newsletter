function checkMyModels() {
  // ANTHROPIC_API_KEY가 상단에 정의되어 있어야 합니다.
  const url = "https://api.openai.com/v1/models";
  try {
    const response = UrlFetchApp.fetch(url, {
      method: "GET",
      headers: {
        "Authorization": "Bearer " + getAPIkey()
      }
    });
    const json = JSON.parse(response.getContentText());
    console.log("--- 사용 가능한 GPT 모델 목록 ---");
    json.data.forEach(m => console.log(m.id));
    console.log("----------------------------------");
    console.log("위 목록 중 하나를 선택해서 아래 2단계 코드의 모델명에 넣으시면 됩니다.");
  } catch (e) {
    console.log("모델 목록을 가져오는 데 실패했습니다. API 키를 확인해 주세요: " + e);
  }
}