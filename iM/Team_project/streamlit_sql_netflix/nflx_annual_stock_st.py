# streamlit_app_tabs.py

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import mysql.connector

# -----------------------------------------
# DB 연결 함수
# -----------------------------------------
def connect_to_database(
    host="10.100.1.82", port=3303, user="teamuser1",
    password="1234", database="our_project_db"
):
    try:
        conn = mysql.connector.connect(
            host=host, port=port, user=user, password=password, database=database
        )
        return conn
    except mysql.connector.Error as err:
        st.error(f"MySQL 연결 오류: {err}")
    return None

# SQL 실행 함수
def sql_to_df(conn, query):
    return pd.read_sql(query, conn)

# 날짜 최근접 스냅
def snap_to_index(dts, target_index):
    dts = pd.to_datetime(pd.Index(dts))
    pos = target_index.get_indexer(dts, method="nearest")
    return target_index[pos]

# 최근접 거래일
def nearest_trading_day(ts, idx: pd.DatetimeIndex):
    pos = idx.get_indexer([pd.to_datetime(ts)], method="nearest")[0]
    return idx[pos]

# -----------------------------------------
# Main App
# -----------------------------------------
def main():
    st.set_page_config(page_title="NFLX 시각화", layout="wide")
    st.title("🎬 Netflix(NFLX) 주가 분석 대시보드")

    conn = connect_to_database()
    if conn is None:
        st.stop()

    # 데이터 로드
    q_stock = """
        SELECT DISTINCT `Date`, `Close`
        FROM our_project_db.nflx_final
        ORDER BY `Date` ASC
    """
    df_stock = sql_to_df(conn, q_stock)
    df_stock["Date"] = pd.to_datetime(df_stock["Date"])
    df_stock["Close"] = pd.to_numeric(df_stock["Close"], errors="coerce")
    df_stock = df_stock.dropna().drop_duplicates(subset=["Date"]).sort_values("Date")

    if df_stock.empty:
        st.error("df_stock이 비어 있습니다.")
        st.stop()

    # 탭 생성
    tab1, tab2, tab3 = st.tabs([
        " 2주봉 & 실적발표 마커",  
        " 실적발표 기준 ±30일 확대",
        "분석 결과"
    ])

    # --------------------------
    # Tab 1
    # --------------------------
    with tab1:
        wk_2w = df_stock.set_index("Date").resample("2W-FRI").last().dropna()
        targets = [pd.Timestamp(f"{y}-12-31") for y in (2021, 2022, 2023, 2024)]
        snap_dates = snap_to_index(targets, wk_2w.index)

        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=wk_2w.index, y=wk_2w["Close"],
                                  mode="lines", name="Close (2W-FRI)"))
        fig1.add_trace(go.Scatter(
            x=snap_dates, y=wk_2w.loc[snap_dates, "Close"],
            mode="markers+text",
            marker=dict(size=12, symbol="star", color="red", line=dict(width=1, color="black")),
            text=[str(y) for y in (2021, 2022, 2023, 2024)],
            textposition="top center",
            name="Year-end marker"
        ))

        fig1.update_layout(title="📊 NFLX Close (2W-FRI) — Year-end Markers",
                           xaxis_title="Date", yaxis_title="Close",
                           template="plotly_white")

        st.plotly_chart(fig1, use_container_width=True)
        st.markdown("""
        - **마커는 넷플릭스의 연간 실적 발표일 기준입니다.**
        - **단, 매년 12월 31일로 스냅된 값이 실제 발표일과 정확히 일치하지 않을 수 있습니다.**
        """)

        # 수익률 요약
        start_price = df_stock['Close'].iloc[0]
        end_price = df_stock['Close'].iloc[1102] if len(df_stock) > 1102 else df_stock['Close'].iloc[-1]
        years = 5
        total_return = (end_price / start_price - 1) * 100
        avg_return = total_return / years
        cagr = ((end_price / start_price) ** (1/years) - 1) * 100

        st.subheader("📈 5년간 수익률 분석")
        st.markdown(f"""
        - 시작 시점 종가: **${start_price:.2f}**
        - 종료 시점 종가: **${end_price:.2f}**
        - 총 상승률: **{total_return:.2f}%**
        - 연평균 상승률 (단순 평균): **{avg_return:.2f}%**
        - 연평균 상승률 (CAGR): **{cagr:.2f}%**
        """)

        # 연말 종가 및 수익률
        yearly_last = (
            df_stock.set_index("Date")
            .resample("A-DEC")
            .last()
            .dropna(subset=["Close"])
            .loc["2021":"2024"]
        )

        out = yearly_last[["Close"]].rename(columns={"Close": "close_ye"})
        out["prev_close_ye"] = out["close_ye"].shift(1)
        out["yoy_pct"] = ((out["close_ye"] / out["prev_close_ye"] - 1) * 100).round(2)
        out["Year"] = out.index.year
        out = out[["Year", "close_ye", "prev_close_ye", "yoy_pct"]].reset_index(drop=True)

        st.subheader("📋 연말 종가 및 전년 대비 수익률")
        st.dataframe(out, use_container_width=True)

    # --------------------------
    # Tab 2
    # --------------------------
    with tab2:
        st.subheader("🔍 연말 ±30일 확대 차트")
        daily = df_stock.set_index("Date").sort_index()
        years = [2021, 2022, 2023, 2024]
        window_days = 30

        for y in years:
            target = pd.Timestamp(f"{y}-12-31")
            snap = nearest_trading_day(target, daily.index)
            start = snap - pd.Timedelta(days=window_days)
            end = snap + pd.Timedelta(days=window_days)
            seg = daily.loc[start:end].copy()

            try:
                loc = daily.index.get_loc(snap)
                prev_close = daily["Close"].iloc[loc - 1] if loc > 0 else np.nan
                curr_close = daily["Close"].iloc[loc]
                next_close = daily["Close"].iloc[loc + 1] if loc < len(daily) - 1 else np.nan
                ret_prev = (curr_close / prev_close - 1) * 100 if pd.notna(prev_close) else np.nan
                ret_next = (next_close / curr_close - 1) * 100 if pd.notna(next_close) else np.nan
            except:
                ret_prev = ret_next = np.nan

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=seg.index, y=seg["Close"], mode="lines", name="Close (Daily)"
            ))

            if snap in seg.index:
                fig.add_trace(go.Scatter(
                    x=[snap], y=[seg.loc[snap, "Close"]],
                    mode="markers+text",
                    marker=dict(size=12, symbol="star", color="blue", line=dict(width=1, color="black")),
                    text=[f"{y}"], textposition="top center",
                    name="12-31 (snapped)"
                ))
                fig.add_vline(x=snap, line_dash="dash", line_color="gray")

            fig.update_layout(
                title=f"{y} 연말 ±30일 [전일: {ret_prev:.2f}%, 익일: {ret_next:.2f}%]",
                xaxis_title="Date", yaxis_title="Close", template="plotly_white"
            )
            st.plotly_chart(fig, use_container_width=True)

    # --------------------------
    # Tab 3
    # --------------------------
    with tab3:
        st.subheader("분석결과")

        # 실적 발표 후 주가 반응 요약
        st.markdown("""
        <div style="background-color:#f9f9f9; padding:15px; border-radius:8px; border:1px solid #e0e0e0;">
            <h5>연도별 실적 발표 이후 주가 반응 요약</h5>
            <table style='width:100%; border-collapse: collapse;'>
                <tr style='background-color:#f0f0f0;'>
                    <th style='padding:6px;'>연도</th>
                    <th style='padding:6px;'>주가 반응</th>
                    <th style='padding:6px;'>주요 요인</th>
                </tr>
                <tr>
                    <td>2021 Q4</td><td>– 약 20% 하락</td><td>가입자 둔화, 보수적 가이던스, 기술주 약세</td>
                </tr>
                <tr>
                    <td>2022 Q4</td><td>혼조 또는 부정적</td><td>매출 둔화, EPS 급락</td>
                </tr>
                <tr>
                    <td>2023 Q4</td><td>+ 약 12% 상승</td><td>가입자 급증, 예상을 웃돈 실적</td>
                </tr>
                <tr>
                    <td>2024 Q4</td><td>+ 약 14% 상승</td><td>사상 최대 실적, 환매, 가이던스 상향</td>
                </tr>
            </table>
        </div>
        """, unsafe_allow_html=True)

        # 주가에 영향을 주는 주요 요인
        st.markdown("""
        <div style="background-color:#fdfdfd; padding:20px; border-left: 5px solid #409eda; border-radius:6px;">
            <h5>넷플릭스 주가에 영향을 주는 주요 요인</h5>
            <ol>
                <li>유료 가입자 수 증가율</li>
                <li>가이던스 수준</li>
                <li>콘텐츠 전략</li>iM\Team_project\streamlit_sql_netflix\nflx_annual_stock_st.py
                <li>광고 수익 및 요금제 전략</li>
                <li>EPS 등 수익성 지표</li>
                <li>글로벌 금리 및 환율</li>
                <li>경쟁사 동향</li>
                <li>자사주 매입 정책</li>
            </ol>
        </div>
        """, unsafe_allow_html=True)

    conn.close()

if __name__ == "__main__":
    main()
