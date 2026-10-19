"""FilingLens web interface (Streamlit). Talks only to the backend REST API."""
import os

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from frontend import api_client
from frontend.formatting import (
    CONSOLE_PANELS, STATUS_ICONS, fmt_grade, fmt_pct, fmt_points, grafana_panel_url, signal_markdown,
    similarity_caption,
)

GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://localhost:3000")
MLFLOW_UI_URL = os.environ.get("MLFLOW_UI_URL", "http://localhost:5000")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")

st.set_page_config(page_title="FilingLens", page_icon="🔎", layout="wide")


@st.cache_data(ttl=60, show_spinner=False)
def load_tickers() -> list:
    return api_client.get_tickers()["tickers"]


def page_analysis() -> None:
    st.title("🔎 FilingLens")
    st.caption("A plain-English read of what changed in a company's latest annual report (Form 10-K).")
    try:
        tickers = load_tickers()
    except api_client.ApiError as exc:
        st.error(exc.message)
        return

    labels = {f"{t['ticker']}  (latest filing {t['latest_filing_date']})": t["ticker"] for t in tickers}
    choice = st.selectbox("Choose a company (type to search)", list(labels), index=None,
                          placeholder="e.g. AAPL")
    if choice is None:
        st.info("Pick a company above to see how its latest annual report differs from last year's.")
        return

    try:
        with st.spinner("Analysing the filing..."):
            result = api_client.get_analysis(labels[choice])
    except api_client.ApiError as exc:
        st.error(exc.message)
        return

    signal, filing, prev = result["signal"], result["filing"], result["previous_filing"]
    c1, c2, c3 = st.columns(3)
    c1.markdown("**Risk signal**")
    c1.markdown(f"## {signal_markdown(signal['label'])}")
    if signal["score"] is not None:
        c2.metric("Chance of underperforming", fmt_pct(signal["score"]),
                  help="Estimated chance of doing worse than the market over roughly the 6 weeks after filing. Model accuracy could not be "
                       "distinguished from chance, so treat this as one input among many.")
        c2.progress(float(signal["score"]))
    else:
        c2.metric("Chance of underperforming", "n/a")
    c3.metric("Filing date", filing["filing_date"])
    c3.caption(f"Compared with the filing of {prev['filing_date']}" if prev else "No earlier filing to compare with")

    st.subheader("What stands out")
    for reason in result["reasons"]:
        st.markdown(f"- {reason}")

    ch = result["changes"]
    st.subheader("What changed since last year")
    if prev:
        a, b, c, d = st.columns(4)
        a.metric("Risk section length", fmt_pct(ch["risk_section_change_pct"], 0, signed=True))
        b.metric("Wording similarity", fmt_pct(ch["text_similarity"]))
        b.caption(similarity_caption(ch["text_similarity"]))
        c.metric("Uncertainty language", fmt_points(ch["uncertainty_change"]))
        d.metric("Negative-tone language", fmt_points(ch["negative_tone_change"]))
        e, f = st.columns(2)
        e.metric("Litigation-related language", fmt_points(ch["litigious_change"]))
        f.metric("Reading difficulty", fmt_grade(ch["readability_grade_change"]))
        left, right = st.columns(2)
        left.markdown("**Topics given more emphasis**")
        left.write(", ".join(ch["new_terms"]) or "None stand out.")
        right.markdown("**Topics given less emphasis**")
        right.write(", ".join(ch["dropped_terms"]) or "None stand out.")
    else:
        st.write("This is the earliest filing we have for this company, so there is no comparison.")

    with st.expander("Signal across this company's filings"):
        try:
            points = api_client.get_history(result["ticker"])["points"]
            df = pd.DataFrame(points)
            scored = df.dropna(subset=["score"])
            if len(scored) >= 2:
                st.line_chart(scored.set_index("filing_date")["score"], y_label="Estimated chance")
            st.dataframe(df[["filing_date", "label", "score", "text_similarity"]].rename(columns={
                "filing_date": "Filing date", "label": "Signal", "score": "Score",
                "text_similarity": "Similarity to prior year"}), hide_index=True, use_container_width=True)
        except api_client.ApiError as exc:
            st.warning(exc.message)

    if result.get("model"):
        m = result["model"]
        st.caption(f"Model: {m['name']} (version {m['version']}). Held-out ROC-AUC: {m['test_roc_auc']}")
    st.info(result["disclaimer"])


def page_console() -> None:
    st.title("🛠️ Pipeline console")
    st.caption("Status of the data and model pipeline. Intended for the person operating the system.")
    try:
        data = api_client.get_pipeline()
    except api_client.ApiError as exc:
        st.error(exc.message)
        return

    stages = {s["name"]: s for s in data["stages"]}
    parse = stages.get("parse", {}).get("metrics", {})
    champ = data.get("champion") or {}
    a, b, c, d = st.columns(4)
    a.metric("Parse success rate", fmt_pct(parse.get("success_rate"), 1) if parse else "n/a",
             help="Acceptance target: at least 95%.")
    b.metric("Parse throughput", f"{parse.get('filings_per_minute', 'n/a')} filings/min")
    c.metric("Failed filings", data["parse_failure_count"])
    d.metric("Serving model", f"{champ.get('name', 'n/a')} v{champ.get('version', '?')}")

    st.subheader("Pipeline stages")
    st.dataframe(pd.DataFrame([{"Stage": s["name"], "Status": STATUS_ICONS.get(s["status"], s["status"]),
                                "Last updated": s["updated_at"] or "n/a"} for s in data["stages"]]),
                 hide_index=True, use_container_width=True)

    drift = data.get("drift_report")
    if drift and drift.get("status") == "ok":
        st.subheader("Data drift")
        x, y, z = st.columns(3)
        x.metric("Drift detected", "YES" if drift["drift_detected"] else "No")
        y.metric("Drifted features", f"{drift['n_drifted']} of {drift['n_features']}")
        z.metric("Largest PSI", drift["max_psi"], help="Below 0.1 is stable; 0.2 or more is a significant shift.")
        if drift.get("simulated"):
            st.warning("This report uses a deliberately shifted batch (demo). Run the drift check "
                       "again without the simulation flag to restore the real result.")
        rows = [{"Feature": k, "PSI": v["psi"], "KS p-value": v["ks_pvalue"],
                 "Drifted": "yes" if v["drifted"] else "no"} for k, v in drift["features"].items()]
        st.dataframe(pd.DataFrame(rows).sort_values("PSI", ascending=False), hide_index=True,
                     use_container_width=True)
    elif drift:
        st.subheader("Data drift")
        st.info("Not enough recent filings yet to run a reliable drift check.")

    if data.get("events"):
        st.subheader("Recent pipeline events")
        st.dataframe(pd.DataFrame(data["events"]), hide_index=True, use_container_width=True)

    if data["ray_benchmark"]:
        st.subheader("Ray parallel speed-up")
        bench = pd.DataFrame(data["ray_benchmark"])
        st.bar_chart(bench.set_index("workers")["filings_per_minute"], y_label="Filings per minute")
        st.dataframe(bench[["workers", "filings_per_minute", "speedup_vs_1_worker"]], hide_index=True)

    if data["model_comparison"]:
        st.subheader("Model comparison (held-out test period)")
        cols = ["model", "cv_roc_auc", "test_roc_auc", "test_accuracy"]
        st.dataframe(pd.DataFrame(data["model_comparison"])[cols], hide_index=True, use_container_width=True)
    if data["test_uncertainty"]:
        st.caption("95% confidence intervals for the same models:")
        st.dataframe(pd.DataFrame(data["test_uncertainty"]), hide_index=True, use_container_width=True)

    st.subheader("Live monitoring")
    columns = st.columns(2)
    for col_idx, panel_id, title in CONSOLE_PANELS:
        with columns[col_idx]:
            st.markdown(f"**{title}**")
            components.iframe(grafana_panel_url(GRAFANA_URL, panel_id), height=220)
    st.markdown(f"Full tools: [Grafana]({GRAFANA_URL}) · [MLflow experiments]({MLFLOW_UI_URL}) · "
                f"[Prometheus]({PROMETHEUS_URL})")


def page_help() -> None:
    st.title("How to use FilingLens")
    st.markdown("""
**What is this?** Public US companies file a long annual report (Form 10-K) every year. FilingLens
compares a company's latest report with its previous one and highlights what changed in the section
where the company describes its risks.

**How to use it**
1. Open **Company analysis** and choose a company from the list (you can type to search).
2. Read the **risk signal** and **what stands out**.
3. Scroll to **what changed since last year** for the details, and open the history to see earlier years.

**What the signal means.** *Elevated*, *Moderate* or *Lower* reflects a statistical model's estimate of how
likely the stock is to do worse than the overall market over the weeks after the report. In testing, that model
could not be distinguished from chance, so please treat it as one input, never as advice.

**"What stands out"** compares this filing with all the others in our dataset: for example, "the risk section grew
more than 90% of filings". It describes what changed; it does not say why.

**Not enough data** means the company has no earlier filing in our dataset to compare against.

**Limits.** Only the companies in the list are covered. You can't upload your own report or ask free-form questions.
FilingLens is decision support, not financial advice.
""")


PAGES = {"Company analysis": page_analysis, "Pipeline console": page_console, "How to use": page_help}
selected = st.sidebar.radio("Navigate", list(PAGES))
st.sidebar.caption("Decision support only. Not financial advice.")
PAGES[selected]()
