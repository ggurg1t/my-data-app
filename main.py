import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ── 기본 화면 설정 ────────────────────────────────────────────────
st.set_page_config(page_title="어제의 박스오피스", page_icon="🎬", layout="centered")

KOBIS_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"


def get_yesterday_kst() -> str:
    """
    배포 서버의 시계는 한국 시간이 아닐 수 있으므로,
    항상 한국(Asia/Seoul) 기준 '오늘'에서 하루를 뺀 날짜를 yyyymmdd 형식으로 돌려준다.
    (오늘 상영분은 아직 박스오피스 집계가 끝나지 않았기 때문에 어제 날짜를 쓴다)
    """
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    yesterday = now_kst - timedelta(days=1)
    return yesterday.strftime("%Y%m%d")


@st.cache_data(ttl=3600, show_spinner=False)  # 같은 날짜는 1시간 동안 캐시해서 API를 다시 부르지 않음
def fetch_box_office(target_dt: str):
    """
    KOBIS API를 호출해서 (영화 목록 DataFrame, 에러메시지) 튜플을 돌려준다.
    성공하면 에러메시지는 None, 실패하면 DataFrame은 None이 된다.
    """
    try:
        key = st.secrets["KOBIS_KEY"]
    except Exception:
        return None, "인증키(KOBIS_KEY)를 찾을 수 없어요. 스트림릿 클라우드의 Secrets 설정에 KOBIS_KEY를 등록했는지 확인해 주세요."

    params = {"key": key, "targetDt": target_dt}

    try:
        res = requests.get(KOBIS_URL, params=params, timeout=10)
    except requests.exceptions.RequestException:
        return None, "박스오피스 서버에 연결하지 못했어요. 인터넷 연결 상태를 확인하고 잠시 후 다시 시도해 주세요."

    if res.status_code != 200:
        return None, f"박스오피스 서버가 오류를 반환했어요. (상태 코드: {res.status_code})"

    try:
        data = res.json()
    except ValueError:
        return None, "서버 응답을 해석할 수 없었어요. 잠시 후 다시 시도해 주세요."

    # 인증키가 틀려도 상태코드는 200으로 오고, 대신 faultInfo 상자가 온다고 안내받았음
    if "faultInfo" in data:
        message = data["faultInfo"].get("message", "알 수 없는 오류")
        return None, f"인증키를 다시 확인해 주세요. (서버 메시지: {message})"

    try:
        movie_list = data["boxOfficeResult"]["dailyBoxOfficeList"]
    except (KeyError, TypeError):
        return None, "예상하지 못한 응답 형식이에요. KOBIS 서버 상태를 확인해 주세요."

    if not movie_list:
        return None, "해당 날짜의 박스오피스 정보가 비어 있어요. 날짜를 다시 확인해 주세요."

    df = pd.DataFrame(movie_list)

    # ── 숫자 컬럼은 문자열로 오므로 숫자형으로 바꿔준다 (정렬·그래프에 필요) ──
    number_cols = ["rank", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]
    for col in number_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("rank").reset_index(drop=True)
    return df, None


def format_date_kr(target_dt: str) -> str:
    d = datetime.strptime(target_dt, "%Y%m%d")
    return f"{d.year}년 {d.month}월 {d.day}일"


def main():
    st.title("🎬 어제의 박스오피스")

    target_dt = get_yesterday_kst()
    st.caption(f"조회 날짜: {format_date_kr(target_dt)} (한국 시간 기준 어제)")

    with st.spinner("박스오피스 정보를 불러오는 중이에요..."):
        df, error = fetch_box_office(target_dt)

    if error:
        st.error(error)
        return

    # ── 1위 영화: 지표 카드 세 장 ─────────────────────────────────
    top1 = df.iloc[0]
    st.subheader(f"🥇 1위 · {top1['movieNm']}")

    col1, col2, col3 = st.columns(3)
    col1.metric("어제 관객수", f"{int(top1['audiCnt']):,} 명")
    col2.metric("누적 관객수", f"{int(top1['audiAcc']):,} 명")
    col3.metric("스크린수", f"{int(top1['scrnCnt']):,} 개")

    st.divider()

    # ── 관객수 상위 5편 막대그래프 ────────────────────────────────
    st.subheader("📊 관객수 상위 5편")
    top5 = df.sort_values("audiCnt", ascending=False).head(5)
    chart_df = top5.set_index("movieNm")[["audiCnt"]].rename(columns={"audiCnt": "어제 관객수"})
    st.bar_chart(chart_df)

    st.divider()

    # ── 전체 순위표 ──────────────────────────────────────────────
    st.subheader("📋 전체 순위")
    table_df = df[["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
    table_df.columns = ["순위", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]

    st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "관객수": st.column_config.NumberColumn(format="%d 명"),
            "누적관객": st.column_config.NumberColumn(format="%d 명"),
            "스크린수": st.column_config.NumberColumn(format="%d 개"),
        },
    )

    st.caption("자료 출처: 영화진흥위원회(KOBIS) 일별 박스오피스 API")


if __name__ == "__main__":
    main()
