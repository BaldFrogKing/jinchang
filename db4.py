import sqlite3
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime

# ========= 小数位精度控制（最多保留 5 位小数） =========
MAX_DECIMALS = 5


def norm_num(v):
    """录入/解析数值统一规范化：None 保持 None，其余四舍五入到最多 5 位小数"""
    if v is None:
        return None
    return round(float(v), MAX_DECIMALS)


def fmt_display(v):
    """显示用：数值转成最多 5 位小数、去掉多余尾零的字符串；空值显示为空"""
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return str(v)
    if fv == int(fv):
        return str(int(fv))
    return f"{fv:.{MAX_DECIMALS}f}".rstrip("0").rstrip(".")


# ==== streamlit 版本兼容层 ====
def _st_dataframe(df, **kw):
    """兼容新旧 streamlit：新版用 width='stretch'，旧版用 use_container_width=True"""
    df = df.copy()
    for _c in df.columns:
        if pd.api.types.is_numeric_dtype(df[_c]):
            df[_c] = df[_c].map(fmt_display)
    if kw.get('width') == 'stretch':
        kw.pop('width')
        try:
            return st.dataframe(df, width='stretch', **kw)
        except TypeError:
            return st.dataframe(df, use_container_width=True, **kw)
    return st.dataframe(df, **kw)

import os

# ========= 基础配置 =========
DB_PATH = "lab_data.db"

ADMIN_USERNAME = "bf"
ADMIN_PASSWORD = "6224"

VIEW_USERNAME = "viewer"
VIEW_PASSWORD = "1"

# ========= 质量指标看板标准定义 =========
# 来源：金昌实验路线图.docx 中的"质量指标看板"
# 单位统一：全部杂质以%计（1% = 10000ppm），原 ppm 阈值已换算为%。
# 格式: (数据库字段名, 显示名称, 单位, 标准下限, 标准上限, 比较类型)
# 比较类型: "gte"(>=), "lte"(<=), "eq"(=)
STANDARD_INDICATORS = [
    ("d50", "粒径(D50)", "", None, 50, "lte"),
    ("li_content", "Li", "%", 17.8, None, "gte"),
    ("p_content", "P", "%", 26.5, None, "gte"),
    ("purity_content", "含量", "%", 99.0, None, "gte"),
    ("moisture", "水分", "%", None, 0.4, "lte"),
    ("so4_content", "SO4", "%", None, 0.15, "lte"),
    ("cl_content", "Cl", "%", None, 0.01, "lte"),
    ("na_content", "Na", "%", None, 0.025, "lte"),
    ("k_content", "K", "%", None, 0.005, "lte"),
    ("ca_content", "Ca", "%", None, 0.01, "lte"),
    ("mn_content", "Mn", "%", None, 0.001, "lte"),
    ("ni_content", "Ni", "%", None, 0.002, "lte"),
    ("cu_content", "Cu", "%", None, 0.001, "lte"),
    ("pb_content", "Pb", "%", None, 0.001, "lte"),
    ("zn_content", "Zn", "%", None, 0.001, "lte"),
    ("cr_content", "Cr", "%", None, 0.002, "lte"),
    ("mg_content", "Mg", "%", None, 0.01, "lte"),
    ("fe_content", "Fe", "%", None, 0.005, "lte"),
    ("al_content", "Al", "%", None, 0.002, "lte"),
    ("b_content", "B", "%", None, 0.01, "lte"),
    ("magnetic_content", "磁性物", "%", None, 0.0001, "lte"),
    ("magnetic_particles", "磁性金属颗粒", "Pcs/kg", None, 200, "lte"),
    ("cu_zn_particles", "Cu/Zn颗粒", "Pcs/kg", 0, 0, "eq"),
]

# ========= 电池级磷酸二氢锂 看板标准（牌号 LiH2PO4-1） =========
# 来源：YS/T 967《电池级磷酸二氢锂》报批稿 表1（牌号 LiH2PO4-1）及 5.2~5.5。
# 主元素为 ± 区间，用新增比较类型 "range"（low<=值<=high）。
# 全部杂质统一以质量分数%计（1% = 10000ppm），与磷酸锂看板共用同一套%字段，
# 按产品类型各自套用不同的标准阈值，无需再区分 ppm / % 两套录入框。
LH2PO4_STANDARDS = [
    ("p_content",            "P（主元素含量）", "%",      29.55, 29.95, "range"),
    ("li_content",           "Li（主元素含量）", "%",      6.40,  6.80,  "range"),
    ("li_p_ratio",           "Li/P摩尔比",     "",       0.970, 1.030, "range"),
    ("na_content",           "Na",             "%",      None,  0.0070, "lte"),
    ("k_content",            "K",              "%",      None,  0.0030, "lte"),
    ("ca_content",           "Ca",             "%",      None,  0.0020, "lte"),
    ("mg_content",           "Mg",             "%",      None,  0.0020, "lte"),
    ("mn_content",           "Mn",             "%",      None,  0.0010, "lte"),
    ("b_content",            "B",              "%",      None,  0.0020, "lte"),
    ("fe_content",           "Fe",             "%",      None,  0.0020, "lte"),
    ("pb_content",           "Pb",             "%",      None,  0.0010, "lte"),
    ("cu_content",           "Cu",             "%",      None,  0.0010, "lte"),
    ("ni_content",           "Ni",             "%",      None,  0.0005, "lte"),
    ("cr_content",           "Cr",             "%",      None,  0.0010, "lte"),
    ("al_content",           "Al",             "%",      None,  0.0010, "lte"),
    ("co_content",           "Co",             "%",      None,  0.0005, "lte"),
    ("so4_content",          "SO4",            "%",      None,  0.010,  "lte"),
    ("cl_content",           "Cl",             "%",      None,  0.0050, "lte"),
    ("ph_value",             "pH",             "",       3.6,   4.0,   "range"),
    ("moisture",             "水分",           "%",      None,  0.3,   "lte"),
    ("magnetic_ppb_content", "磁性异物",       "μg/kg",  None,  300,   "lte"),
    ("magnetic_particles",   "磁性金属颗粒数", "Pcs/kg", None,  100,   "lte"),
]

# 各产品类型对应看板标准；未列入类型（如"其他"）不做对比。
PRODUCT_STANDARDS = {
    "电池级磷酸锂":   STANDARD_INDICATORS,
    "电池级磷酸二氢锂": LH2PO4_STANDARDS,
}
COMPARE_PRODUCT_TYPES = set(PRODUCT_STANDARDS.keys())
NO_STANDARD_TEXT = "暂无标准"

def get_standards(product_type):
    """按产品类型取对应看板标准列表；无则返回空列表。"""
    return PRODUCT_STANDARDS.get((product_type or "").strip(), [])

def get_standard_map(product_type):
    """按产品类型取 {字段名: 标准元组} 映射。"""
    return {s[0]: s for s in get_standards(product_type)}

# ========= 指标输入与达标判定工具 =========
NOT_TESTED_TEXT = "未检测"


def parse_metric(text):
    """把输入框文本解析为数值；留空或填"未检测"等非数值一律视为未检测(None)"""
    if text is None:
        return None
    t = str(text).strip()
    if t == "" or t in (NOT_TESTED_TEXT, "-", "--", "无", "/"):
        return None
    t = t.replace("，", ".").replace("。", ".")
    try:
        return norm_num(float(t))
    except ValueError:
        return None


def metric_input(field, label, unit="", placeholder="留空 = 未检测"):
    """统一的指标输入框：返回 float 或 None（None 表示未检测）"""
    show = f"{label}（{unit}）" if unit else label
    return parse_metric(st.text_input(show, key=f"inp_{field}", placeholder=placeholder))


def standard_range_text(unit, low, high, cmp_type):
    if cmp_type == "gte":
        return f">={low}{unit}"
    if cmp_type == "lte":
        return f"<={high}{unit}"
    if cmp_type == "eq":
        return f"={high}{unit}"
    if cmp_type == "range":
        return f"{low}~{high}{unit}"
    return "未定义"


def check_indicator(value, low, high, cmp_type):
    """单项判定：True 达标 / False 不达标；未检测不参与判定"""
    if value is None or pd.isna(value):
        return True
    if cmp_type == "gte":
        return value >= low
    if cmp_type == "lte":
        return value <= high
    if cmp_type == "eq":
        return value == high
    if cmp_type == "range":
        return low <= value <= high
    return True


def evaluate_standard(values, product_type=None):
    """按对应产品类型的看板标准自动达标判定。
       该产品类型无看板标准 -> ('不对比', [])；
       已检测项全部达标->达标；任一项超标->不达标；全未检测->未检测。"""
    standards = get_standards(product_type)
    if not standards:
        return "不对比", []
    checked = 0
    failed = []
    for key, name, unit, low, high, cmp_type in standards:
        v = values.get(key)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        checked += 1
        if not check_indicator(v, low, high, cmp_type):
            failed.append(f"{name}={v}{unit}（标准 {standard_range_text(unit, low, high, cmp_type)}）")
    if checked == 0:
        return NOT_TESTED_TEXT, []
    if failed:
        return "不达标", failed
    return "达标", []


# 录入表单指标分组（字段名, 显示名, 单位）——字段名与数据库列一一对应
BASIC_FIELDS = [
    ("li_content", "锂含量 Li", "%"),
    ("p_content", "磷含量 P", "%"),
    ("na_content", "钠含量 Na", "%"),
    ("ca_content", "钙含量 Ca", "%"),
    ("mg_content", "镁含量 Mg", "%"),
    ("b_content", "硼含量 B", "%"),
    ("si_content", "硅含量 Si", "%"),
    ("cl_content", "氯离子 Cl", "%"),
    ("al_content", "铝含量 Al", "%"),
    ("fe_content", "铁含量 Fe", "%"),
    ("co3_content", "碳酸根 CO3", "%"),
    ("so4_content", "硫酸根 SO4", "%"),
    ("moisture", "含水量/水分", "%"),
]

BOARD_EXTRA_FIELDS = [
    ("k_content", "钾含量 K", "%"),
    ("mn_content", "锰含量 Mn", "%"),
    ("ni_content", "镍含量 Ni", "%"),
    ("cu_content", "铜含量 Cu", "%"),
    ("pb_content", "铅含量 Pb", "%"),
    ("zn_content", "锌含量 Zn", "%"),
    ("cr_content", "铬含量 Cr", "%"),
    ("magnetic_content", "磁性物", "%"),
    ("magnetic_particles", "磁性金属颗粒", "Pcs/kg"),
    ("cu_zn_particles", "Cu/Zn颗粒", "Pcs/kg"),
    ("d50", "粒径(D50)", ""),
    ("purity_content", "含量/纯度", "%"),
]

MASS_FIELDS = [
    ("raw_li_mass", "原料锂质量", "g"),
    ("raw_p_mass", "原料磷质量", "g"),
    ("added_li_mass", "添加锂质量", "g"),
    ("added_p_mass", "添加磷质量", "g"),
    ("product_li_mass", "产物中锂质量", "g"),
    ("product_p_mass", "产物中磷质量", "g"),
]

# 新增可录入指标：钴、pH、Li/P摩尔比、磁性异物(μg/kg)。
# 其余各元素杂质已统一为%单位，直接复用上方 BASIC_FIELDS / BOARD_EXTRA_FIELDS 字段。
NEW_INPUT_FIELDS = [
    ("co_content",           "钴含量 Co",          "%"),
    ("ph_value",             "pH值",               ""),
    ("li_p_ratio",           "Li/P摩尔比",         ""),
    ("magnetic_ppb_content", "磁性异物",           "μg/kg"),
]

ALL_INPUT_FIELDS = BASIC_FIELDS + BOARD_EXTRA_FIELDS + NEW_INPUT_FIELDS
NEW_DB_COLUMNS = [f for f, _, _ in NEW_INPUT_FIELDS]

FIELD_DISPLAY = {f: (lbl, unit) for f, lbl, unit in ALL_INPUT_FIELDS}
for _s in STANDARD_INDICATORS + LH2PO4_STANDARDS:
    FIELD_DISPLAY.setdefault(_s[0], (_s[1], _s[2]))


# ========= 数据库初始化 =========
# ========= 历史数据库单位迁移：ppm -> % （1% = 10000ppm） =========
# 旧版把部分杂质按 ppm 存储；本版本统一为%，故对老库做一次性换算。
# 规则：同名指标若存在 *_pct 列（磷酸二氢锂曾按%录入）则优先取%列，否则把 ppm 值除以 10000。
# 通过 schema_meta 标记，确保只执行一次。
_PPM_PCT_PAIRS = [
    ("na_content", "na_pct_content"), ("k_content", "k_pct_content"),
    ("ca_content", "ca_pct_content"), ("mg_content", "mg_pct_content"),
    ("mn_content", "mn_pct_content"), ("b_content", "b_pct_content"),
    ("fe_content", "fe_pct_content"), ("pb_content", "pb_pct_content"),
    ("cu_content", "cu_pct_content"), ("ni_content", "ni_pct_content"),
    ("cr_content", "cr_pct_content"), ("al_content", "al_pct_content"),
    ("co_content", "co_pct_content"), ("cl_content", "cl_pct_content"),
]
_PPM_ONLY_COLS = ["si_content", "co3_content", "zn_content", "magnetic_content"]


def _migrate_ppm_to_pct(cursor):
    cursor.execute("CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT)")
    row = cursor.execute("SELECT value FROM schema_meta WHERE key='unit_ppm_to_pct'").fetchone()
    if row and row[0] == "done":
        return
    cursor.execute("PRAGMA table_info(test_results)")
    cols = {r[1] for r in cursor.fetchall()}
    if "test_results" not in {t[0] for t in cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}:
        return
    for base, pct in _PPM_PCT_PAIRS:
        if base not in cols:
            continue
        if pct in cols:
            cursor.execute(
                f"UPDATE test_results SET {base}=COALESCE({pct}, ROUND({base}/10000.0, 5))")
        else:
            cursor.execute(f"UPDATE test_results SET {base}=ROUND({base}/10000.0, 5)")
    for col in _PPM_ONLY_COLS:
        if col in cols:
            cursor.execute(f"UPDATE test_results SET {col}=ROUND({col}/10000.0, 5)")
    cursor.execute("INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('unit_ppm_to_pct', 'done')")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 创建samples表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS samples (
            sample_id TEXT PRIMARY KEY,
            product_type TEXT,
            process_route TEXT,
            batch_number TEXT,
            test_date TEXT,
            tester TEXT,
            remark TEXT
        )
    """)

    # 创建test_results表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id TEXT,

            -- 检测指标 - 基础
            li_content REAL,
            p_content REAL,
            na_content REAL,
            ca_content REAL,
            mg_content REAL,
            b_content REAL,
            si_content REAL,
            cl_content REAL,
            al_content REAL,
            fe_content REAL,
            co3_content REAL,
            so4_content REAL,
            moisture REAL,

            -- 检测指标 - 看板新增
            k_content REAL,
            mn_content REAL,
            ni_content REAL,
            cu_content REAL,
            pb_content REAL,
            zn_content REAL,
            cr_content REAL,
            magnetic_content REAL,
            magnetic_particles REAL,
            cu_zn_particles REAL,
            d50 REAL,
            purity_content REAL,

            -- 新增可录入指标（钴/pH/Li比/磁性异物μg/kg + 各元素%单位版本）
            co_content REAL,
            ph_value REAL,
            li_p_ratio REAL,
            magnetic_ppb_content REAL,
            na_pct_content REAL,
            k_pct_content REAL,
            ca_pct_content REAL,
            mg_pct_content REAL,
            b_pct_content REAL,
            fe_pct_content REAL,
            pb_pct_content REAL,
            cu_pct_content REAL,
            ni_pct_content REAL,
            cr_pct_content REAL,
            al_pct_content REAL,
            co_pct_content REAL,
            cl_pct_content REAL,

            -- 收率计算相关
            raw_li_mass REAL,
            raw_p_mass REAL,
            added_li_mass REAL,
            added_p_mass REAL,
            product_li_mass REAL,
            product_p_mass REAL,

            li_recovery REAL,
            p_recovery REAL,

            standard_grade TEXT,

            FOREIGN KEY(sample_id) REFERENCES samples(sample_id)
        )
    """)

    # 为已有数据库动态添加新列
    all_possible_columns = [
        "k_content", "mn_content", "ni_content", "cu_content", "pb_content",
        "zn_content", "cr_content", "magnetic_content", "magnetic_particles",
        "cu_zn_particles", "d50", "purity_content",
        "product_li_mass", "product_p_mass"
    ] + NEW_DB_COLUMNS

    cursor.execute("PRAGMA table_info(test_results)")
    existing_cols = [row[1] for row in cursor.fetchall()]

    for col in all_possible_columns:
        if col not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE test_results ADD COLUMN {col} REAL")
            except Exception:
                pass

    # samples表加remark列
    cursor.execute("PRAGMA table_info(samples)")
    sample_cols = [row[1] for row in cursor.fetchall()]
    if "remark" not in sample_cols:
        try:
            cursor.execute("ALTER TABLE samples ADD COLUMN remark TEXT")
        except Exception:
            pass

    _migrate_ppm_to_pct(cursor)

    conn.commit()
    conn.close()

# ========= 收率计算 =========
def calculate_recovery(product_li_mass, product_p_mass,
                       raw_li_mass, raw_p_mass,
                       added_li_mass, added_p_mass):
    """收率计算：
       锂收率 = 产物中锂质量 / (原料锂质量 + 添加锂质量) * 100
       磷收率 = 产物中磷质量 / (原料磷质量 + 添加磷质量) * 100
       分子或分母缺数据则该项收率留空，不做达标判定。"""
    li_recovery = None
    p_recovery = None

    if product_li_mass is not None and (raw_li_mass or added_li_mass):
        total_li_input = (raw_li_mass or 0.0) + (added_li_mass or 0.0)
        if total_li_input > 0:
            li_recovery = round(product_li_mass / total_li_input * 100, MAX_DECIMALS)

    if product_p_mass is not None and (raw_p_mass or added_p_mass):
        total_p_input = (raw_p_mass or 0.0) + (added_p_mass or 0.0)
        if total_p_input > 0:
            p_recovery = round(product_p_mass / total_p_input * 100, MAX_DECIMALS)

    return li_recovery, p_recovery

# ========= 保存前统一校验：负数禁止 + 收率>100%拦截 =========
def validate_submission(data):
    """返回错误信息列表；为空表示通过。规则：
       1) 所有检测指标与收率相关质量字段一律禁止负数（0 与正数允许，留空不算）；
       2) 锂/磷收率计算结果大于 100% 判为数据错误（等于 100% 允许）；
       3) 分子/分母缺失、算不出收率的不触发收率校验。"""
    errors = []

    numeric_fields = (
        [f for f, _, _ in BASIC_FIELDS]
        + [f for f, _, _ in BOARD_EXTRA_FIELDS]
        + [f for f, _, _ in NEW_INPUT_FIELDS]
        + [f for f, _, _ in MASS_FIELDS]
    )
    label_map = {f: lbl for f, lbl, _ in
                 (BASIC_FIELDS + BOARD_EXTRA_FIELDS + NEW_INPUT_FIELDS + MASS_FIELDS)}

    for key in numeric_fields:
        v = data.get(key)
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv < 0:
            errors.append(f"{label_map.get(key, key)} 不能为负数（当前值：{fmt_display(v)}）")

    if errors:
        return errors

    li_recovery, p_recovery = calculate_recovery(
        data.get("product_li_mass"),
        data.get("product_p_mass"),
        data.get("raw_li_mass"),
        data.get("raw_p_mass"),
        data.get("added_li_mass"),
        data.get("added_p_mass"),
    )
    if li_recovery is not None and li_recovery > 100:
        errors.append(f"锂收率 {fmt_display(li_recovery)}% 大于 100%，请核对原料/添加/产物中的锂质量后再保存。")
    if p_recovery is not None and p_recovery > 100:
        errors.append(f"磷收率 {fmt_display(p_recovery)}% 大于 100%，请核对原料/添加/产物中的磷质量后再保存。")

    return errors



# ========= 数据备份：导出 / 导入 =========
def _export_backup_bytes():
    conn = sqlite3.connect(DB_PATH)
    samples_df = pd.read_sql_query("SELECT * FROM samples", conn)
    results_df = pd.read_sql_query("SELECT * FROM test_results", conn)
    conn.close()
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        samples_df.to_excel(writer, index=False, sheet_name="samples")
        results_df.to_excel(writer, index=False, sheet_name="test_results")
    return output.getvalue(), len(samples_df), len(results_df)


def _import_backup_bytes(uploaded):
    import io as _io
    xls = pd.ExcelFile(_io.BytesIO(uploaded.getvalue()))
    samples_df = pd.read_excel(xls, sheet_name="samples")
    results_df = pd.read_excel(xls, sheet_name="test_results")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM test_results")
    cur.execute("DELETE FROM samples")
    if not samples_df.empty:
        cols = [c for c in samples_df.columns if c != "id"]
        col_str = ",".join(cols)
        placeholders = ",".join(["?"] * len(cols))
        for _, row in samples_df.iterrows():
            vals = [None if pd.isna(row[c]) else row[c] for c in cols]
            cur.execute(f"INSERT OR REPLACE INTO samples ({col_str}) VALUES ({placeholders})", vals)
    if not results_df.empty:
        cols = [c for c in results_df.columns if c != "id"]
        col_str = ",".join(cols)
        placeholders = ",".join(["?"] * len(cols))
        for _, row in results_df.iterrows():
            vals = [None if pd.isna(row[c]) else row[c] for c in cols]
            cur.execute(f"INSERT INTO test_results ({col_str}) VALUES ({placeholders})", vals)
    conn.commit()
    ns, nr = len(samples_df), len(results_df)
    conn.close()
    return ns, nr

# ========= 数据录入 =========
def add_sample_and_result(data):
    errs = validate_submission(data)
    if errs:
        st.error("数据错误，未能保存：\n\n" + "\n\n".join("- " + e for e in errs))
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO samples
            (sample_id, product_type, process_route, batch_number, test_date, tester, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data["sample_id"], data["product_type"], data["process_route"],
            data["batch_number"], data["test_date"], data["tester"], data["remark"],
        ))

        grade, grade_failed = evaluate_standard(data, data.get("product_type"))
        data["standard_grade"] = grade

        li_recovery, p_recovery = calculate_recovery(
            data.get("product_li_mass"), data.get("product_p_mass"),
            data.get("raw_li_mass"), data.get("raw_p_mass"),
            data.get("added_li_mass"), data.get("added_p_mass"),
        )

        metric_fields = [f for f, _, _ in ALL_INPUT_FIELDS]
        cols = (["sample_id"] + metric_fields + [
            "raw_li_mass", "raw_p_mass", "added_li_mass", "added_p_mass",
            "product_li_mass", "product_p_mass",
            "li_recovery", "p_recovery", "standard_grade",
        ])
        col_sql = ",".join(cols)
        placeholders = ",".join(["?"] * len(cols))
        vals = ([data["sample_id"]]
                + [data.get(f) for f in metric_fields]
                + [data.get("raw_li_mass"), data.get("raw_p_mass"),
                   data.get("added_li_mass"), data.get("added_p_mass"),
                   data.get("product_li_mass"), data.get("product_p_mass"),
                   li_recovery, p_recovery, data["standard_grade"]])

        cursor.execute(f"INSERT INTO test_results ({col_sql}) VALUES ({placeholders})", vals)
        conn.commit()

        msg = "数据保存成功。"
        if li_recovery is not None:
            msg += f" 锂收率：{li_recovery}%"
        if p_recovery is not None:
            msg += f" 磷收率：{p_recovery}%"
        st.success(msg)
        if grade_failed:
            st.warning("以下指标超出看板标准：" + "；".join(grade_failed))

    except Exception as e:
        conn.rollback()
        st.error(f"保存失败：{e}")
    finally:
        conn.close()


# ========= 查询函数 =========
def query_by_sample_id(sample_id):
    conn = sqlite3.connect(DB_PATH)
    r_cols = ", ".join("r." + f for f, _, _ in ALL_INPUT_FIELDS)
    sql = f"""
        SELECT s.sample_id, s.product_type, s.process_route, s.batch_number,
               s.test_date, s.tester, s.remark,
               {r_cols},
               r.raw_li_mass, r.raw_p_mass, r.added_li_mass, r.added_p_mass,
               r.product_li_mass, r.product_p_mass,
               r.li_recovery, r.p_recovery, r.standard_grade
        FROM samples s
        LEFT JOIN test_results r ON s.sample_id = r.sample_id
        WHERE s.sample_id = ?
    """
    df = pd.read_sql_query(sql, conn, params=(sample_id,))
    conn.close()
    return df


def query_all_results():
    conn = sqlite3.connect(DB_PATH)
    r_cols = ", ".join("r." + f for f, _, _ in ALL_INPUT_FIELDS)
    sql = f"""
        SELECT s.sample_id, s.product_type, s.process_route, s.batch_number,
               s.test_date, s.tester, s.remark,
               {r_cols},
               r.li_recovery, r.p_recovery, r.standard_grade
        FROM samples s
        LEFT JOIN test_results r ON s.sample_id = r.sample_id
        ORDER BY s.test_date DESC
    """
    df = pd.read_sql_query(sql, conn)
    conn.close()
    return df


def _build_slim_sql():
    cols = """
            SELECT s.sample_id,
                   s.product_type,
                   s.batch_number,
                   s.test_date,
                   s.tester,
                   s.remark,
                   r.li_recovery,
                   r.p_recovery,
                   r.standard_grade
            FROM samples s
            LEFT JOIN test_results r ON s.sample_id = r.sample_id
    """
    return cols


def search_samples(product_type=None, tester=None, remark=None):
    """按 产品类型 / 实验人员 / 备注关键词 任意组合(AND)筛选。
    仅把填了值的条件拼进 WHERE，留空的条件自动忽略。"""
    conds, params = [], []
    if product_type and product_type != "全部类型":
        conds.append("s.product_type = ?")
        params.append(product_type)
    if tester:
        conds.append("s.tester LIKE ?")
        params.append(f"%{tester}%")
    if remark:
        conds.append("s.remark LIKE ?")
        params.append(f"%{remark}%")
    sql = _build_slim_sql()
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY s.test_date DESC"
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(sql, conn, params=tuple(params))
    conn.close()
    return df


def search_by_remark(keyword, product_type=None):
    """按备注关键词模糊搜索，可选按产品类型过滤"""
    conn = sqlite3.connect(DB_PATH)
    if product_type and product_type != "全部类型":
        df = pd.read_sql_query("""
            SELECT s.sample_id,
                   s.product_type,
                   s.batch_number,
                   s.test_date,
                   s.tester,
                   s.remark,
                   r.li_recovery,
                   r.p_recovery,
                   r.standard_grade
            FROM samples s
            LEFT JOIN test_results r ON s.sample_id = r.sample_id
            WHERE s.remark LIKE ? AND s.product_type = ?
            ORDER BY s.test_date DESC
        """, conn, params=(f"%{keyword}%", product_type))
    else:
        df = pd.read_sql_query("""
            SELECT s.sample_id,
                   s.product_type,
                   s.batch_number,
                   s.test_date,
                   s.tester,
                   s.remark,
                   r.li_recovery,
                   r.p_recovery,
                   r.standard_grade
            FROM samples s
            LEFT JOIN test_results r ON s.sample_id = r.sample_id
            WHERE s.remark LIKE ?
            ORDER BY s.test_date DESC
        """, conn, params=(f"%{keyword}%",))
    conn.close()
    return df

# ========= 查询结果附加"逐项是否达标"列 =========
def _item_status(v, low, high, cmp_type):
    """单值对单一标准 -> 达标/不达标/未检测"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return NOT_TESTED_TEXT
    return "达标" if check_indicator(v, low, high, cmp_type) else "不达标"


def with_compliance_columns(df):
    """给查询结果每一行按看板标准逐项追加"{指标}·是否达标"列，并移除旧的总判定列"""
    if df.empty:
        return df
    df = df.copy()
    if "standard_grade" in df.columns:
        df = df.drop(columns=["standard_grade"])
    for key, name, unit, low, high, cmp_type in STANDARD_INDICATORS:
        if key in df.columns:
            df[f"{name}·是否达标"] = df[key].map(lambda v: _item_status(v, low, high, cmp_type))
    return df


# ========= 删除数据 =========
def list_sample_ids():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT sample_id, test_date, batch_number FROM samples ORDER BY test_date DESC",
        conn,
    )
    conn.close()
    return df


def delete_sample(sample_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM test_results WHERE sample_id = ?", (sample_id,))
        cursor.execute("DELETE FROM samples WHERE sample_id = ?", (sample_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"删除失败：{e}")
        return False
    finally:
        conn.close()


def sample_exists(sample_id):
    """库中 samples 表是否已有该样品编号"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM samples WHERE sample_id = ? LIMIT 1", (sample_id,))
    found = cur.fetchone() is not None
    conn.close()
    return found


def overwrite_sample(data):
    """覆盖原数据：先删除该样品旧的检测结果与样品信息，再重新写入。
       校验不通过则不删除、不覆盖，避免误删原数据。"""
    errs = validate_submission(data)
    if errs:
        st.error("数据错误，未能覆盖保存：\n\n" + "\n\n".join("- " + e for e in errs))
        return

    sid = data["sample_id"]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM test_results WHERE sample_id = ?", (sid,))
    cur.execute("DELETE FROM samples WHERE sample_id = ?", (sid,))
    conn.commit()
    conn.close()
    add_sample_and_result(data)


# ========= 指标对比（使用看板标准） =========
def compare_with_standard(df):
    if df.empty:
        st.warning("没有查询到数据")
        return

    row = df.iloc[0]
    ptype = str(row.get("product_type", "") or "").strip()
    standards = get_standards(ptype)
    if not standards:
        st.info("该产品类型为「" + (ptype or "未填写") +
                "」，目前缺少对应的质量看板数据，不进行指标对比。")
        return

    st.subheader(f"「{ptype}」质量指标看板 - 对比结果")
    std_map = get_standard_map(ptype)

    ordered = [s[0] for s in standards]
    for f, _lbl, _unit in ALL_INPUT_FIELDS:
        if f not in ordered:
            ordered.append(f)

    compare_data = []
    for key in ordered:
        v = row.get(key)
        name, unit = FIELD_DISPLAY.get(key, (key, ""))
        if key in std_map:
            _, _, u, low, high, cmp_type = std_map[key]
            range_t = standard_range_text(u, low, high, cmp_type)
            status = NOT_TESTED_TEXT if _is_null(v) else ("达标" if check_indicator(v, low, high, cmp_type) else "不达标")
        else:
            range_t = "—"
            status = NO_STANDARD_TEXT if not _is_null(v) else NOT_TESTED_TEXT
        compare_data.append({
            "指标": name,
            "实测值": (NOT_TESTED_TEXT if _is_null(v) else f"{fmt_display(v)}{unit}"),
            "标准范围": range_t,
            "是否达标": status,
        })

    _st_dataframe(pd.DataFrame(compare_data), width="stretch")


def _is_null(v):
    return v is None or (isinstance(v, float) and pd.isna(v))


def render_sample_detail(df):
    """单样品纵向详情：基本信息 + 逐项指标达标 + 收率数据"""
    if df.empty:
        st.warning("没有查询到数据")
        return
    row = df.iloc[0]

    def g(key):
        v = row.get(key)
        return "" if _is_null(v) else v

    info_pairs = [
        ("样品编号", g("sample_id")), ("产品类型", g("product_type")),
        ("工艺路线", g("process_route")), ("检测日期", g("test_date")),
        ("实验人员", g("tester")), ("备注", g("remark")),
    ]
    st.subheader("基本信息")
    _st_dataframe(pd.DataFrame({"项目": [p[0] for p in info_pairs],
                                "内容": [p[1] for p in info_pairs]}), width="stretch")

    ptype = str(row.get("product_type", "") or "").strip()
    standards = get_standards(ptype)
    std_map = get_standard_map(ptype)

    if standards:
        st.subheader(f"检测指标（逐项对照「{ptype}」看板固定标准）")
    else:
        st.subheader("检测指标（实测值）")
        st.info("该产品类型为「" + (ptype or "未填写") +
                "」，目前缺少对应的质量看板数据，不进行达标对比，仅展示实测值。")

    ordered = [s[0] for s in standards]
    for f, _lbl, _unit in ALL_INPUT_FIELDS:
        if f not in ordered:
            ordered.append(f)

    rows = []
    for key in ordered:
        v = row.get(key)
        name, unit = FIELD_DISPLAY.get(key, (key, ""))
        item = {"指标": name,
                "实测值": (NOT_TESTED_TEXT if _is_null(v) else f"{fmt_display(v)}{unit}")}
        if key in std_map:
            _, _, u, low, high, cmp_type = std_map[key]
            item["标准范围"] = standard_range_text(u, low, high, cmp_type)
            item["是否达标"] = _item_status(v, low, high, cmp_type)
        elif standards:
            item["标准范围"] = "—"
            item["是否达标"] = NO_STANDARD_TEXT if not _is_null(v) else NOT_TESTED_TEXT
        rows.append(item)

    if standards:
        _st_dataframe(pd.DataFrame(rows), width="stretch")
    else:
        _st_dataframe(pd.DataFrame([{"指标": r["指标"], "实测值": r["实测值"]} for r in rows]), width="stretch")

    st.subheader("收率计算数据")
    rec_pairs = [
        ("原料锂质量(g)", g("raw_li_mass")), ("添加锂质量(g)", g("added_li_mass")),
        ("产物中锂质量(g)", g("product_li_mass")),
        ("锂收率", "" if _is_null(row.get("li_recovery")) else f"{fmt_display(row.get('li_recovery'))}%"),
        ("原料磷质量(g)", g("raw_p_mass")), ("添加磷质量(g)", g("added_p_mass")),
        ("产物中磷质量(g)", g("product_p_mass")),
        ("磷收率", "" if _is_null(row.get("p_recovery")) else f"{fmt_display(row.get('p_recovery'))}%"),
    ]
    _st_dataframe(pd.DataFrame({"项目": [p[0] for p in rec_pairs],
                                "数值": [p[1] for p in rec_pairs]}), width="stretch")


def render_results_vertical(df):
    """多样品结果：指标为行、样品编号为列，纵向呈现；逐行按其产品类型对照各自看板标准"""
    if df.empty:
        st.warning("没有可展示的数据")
        return
    df = df.copy()
    if "standard_grade" in df.columns:
        df = df.drop(columns=["standard_grade"])

    sids = [str(s) for s in df["sample_id"].tolist()]
    n = len(df)
    ptypes = [str(df.iloc[i].get("product_type", "") or "").strip() for i in range(n)]
    std_maps = [get_standard_map(pt) for pt in ptypes]
    has_std = [bool(get_standards(pt)) for pt in ptypes]

    def col_of(key):
        return [df.iloc[i].get(key) for i in range(n)]

    row_items = []
    for label, key in [("产品类型", "product_type"), ("工艺路线", "process_route"),
                       ("检测日期", "test_date"), ("实验人员", "tester"), ("备注", "remark")]:
        if key in df.columns:
            vals = col_of(key)
            row_items.append((label, [("" if _is_null(v) else fmt_display(v)) for v in vals]))

    for key, _name, _unit in ALL_INPUT_FIELDS:
        if key in df.columns:
            name, unit = FIELD_DISPLAY.get(key, (key, ""))
            vals = col_of(key)
            row_items.append(((f"{name}({unit})" if unit else name) + "·实测",
                              [(NOT_TESTED_TEXT if _is_null(v) else f"{fmt_display(v)}{unit}") for v in vals]))
            stat = []
            for i in range(n):
                v = vals[i]
                smap = std_maps[i]
                if key in smap:
                    _, _, u, low, high, cmp_type = smap[key]
                    stat.append(_item_status(v, low, high, cmp_type))
                elif has_std[i]:
                    stat.append(NO_STANDARD_TEXT if not _is_null(v) else NOT_TESTED_TEXT)
                else:
                    stat.append("不对比")
            row_items.append((f"{name}·是否达标", stat))

    for label, key in [("锂收率", "li_recovery"), ("磷收率", "p_recovery")]:
        if key in df.columns:
            vals = col_of(key)
            row_items.append((label, [("" if _is_null(v) else f"{fmt_display(v)}%") for v in vals]))

    data = {}
    for i, sid in enumerate(sids):
        data[sid] = [vals[i] for _, vals in row_items]
    out = pd.DataFrame(data, index=[lbl for lbl, _ in row_items])
    out.index.name = "指标"
    out = out.reset_index()
    _st_dataframe(out, width="stretch")


# ========= 样品间对比（整体对比，不画图） =========
# 对比表中展示的指标列（检测指标 + 收率），顺序即展示顺序
COMPARE_INDICATOR_KEYS = [f for f, _, _ in ALL_INPUT_FIELDS] + ["li_recovery", "p_recovery"]
COMPARE_META_KEYS = [("product_type", "产品类型"), ("tester", "实验人员"),
                    ("test_date", "检测日期"), ("batch_number", "批次号"), ("remark", "备注")]


def compare_samples(sample_ids):
    """对所选样品做整体对比：所有可录入指标逐项并排展示，不选指标、不画图。
    未录入的指标统一显示"未录入"；用列字典法构造，彻底避免列数错位报错。"""
    sample_ids = [s for s in dict.fromkeys(sample_ids) if s]  # 去重保序
    if len(sample_ids) < 1:
        st.warning("请至少选择一个样品编号")
        return

    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join(["?"] * len(sample_ids))
    cols = ["s.sample_id"] + [f"r.{f}" for f in COMPARE_INDICATOR_KEYS] \
        + [f"s.{f}" for f, _ in COMPARE_META_KEYS]
    sql = (
        f"SELECT {', '.join(cols)} FROM samples s "
        f"LEFT JOIN test_results r ON s.sample_id = r.sample_id "
        f"WHERE s.sample_id IN ({placeholders})"
    )
    df = pd.read_sql_query(sql, conn, params=sample_ids)
    conn.close()

    if df.empty:
        st.warning("未找到所选样品的对比数据")
        return

    found_ids = list(df["sample_id"])
    missing = [s for s in sample_ids if s not in found_ids]
    if missing:
        st.warning(f"以下编号未找到数据，已自动跳过：{'、'.join(missing)}")

    df = df.set_index("sample_id")
    ordered = [s for s in sample_ids if s in df.index]
    if not ordered:
        return
    df = df.loc[ordered]  # 按用户选择顺序排列

    def _is_empty(v):
        if v is None:
            return True
        if isinstance(v, float) and pd.isna(v):
            return True
        if isinstance(v, str) and v.strip() == "":
            return True
        return False

    # 以"指标"为行、样品编号为列，列字典法构造：
    # 每个样品一列、每个指标一行，列长度恒等于指标行数，绝不会出现列数错位。
    row_labels = []
    columns_data = {sid: [] for sid in ordered}

    # 1) 基础信息行
    for key, label in COMPARE_META_KEYS:
        row_labels.append(label)
        for sid in ordered:
            if key in df.columns:
                raw = df.at[sid, key]
                columns_data[sid].append("未录入" if _is_empty(raw) else str(raw))
            else:
                columns_data[sid].append("未录入")

    # 2) 全部可录入检测指标 + 收率（缺列也补一行，统一显示未录入）
    for key in COMPARE_INDICATOR_KEYS:
        lbl, unit = FIELD_DISPLAY.get(key, (key, ""))
        head = f"{lbl}（{unit}）" if unit else lbl
        row_labels.append(head)
        for sid in ordered:
            if key in df.columns:
                raw = df.at[sid, key]
                if _is_empty(raw):
                    columns_data[sid].append("未录入")
                else:
                    try:
                        columns_data[sid].append(fmt_display(raw))
                    except Exception:
                        columns_data[sid].append(str(raw))
            else:
                columns_data[sid].append("未录入")

    out_df = pd.DataFrame(columns_data, index=row_labels)
    out_df.index.name = "指标"
    out_df = out_df.reset_index()

    n_indicator = len(row_labels) - len(COMPARE_META_KEYS)
    st.success(f"正在对 {len(ordered)} 个样品进行整体对比（共展示 {n_indicator} 项可录入指标）")
    _st_dataframe(out_df, width="stretch")


# ========= 登录状态 =========
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None

if "selected_sample_id" not in st.session_state:
    st.session_state.selected_sample_id = None

def login_page():
    st.title("金昌北方国能实验数据系统登录")

    username = st.text_input("用户名")
    password = st.text_input("密码", type="password")

    if st.button("登录"):
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            st.session_state.logged_in = True
            st.session_state.role = "admin"
            st.success("管理员登录成功")
            st.rerun()
        elif username == VIEW_USERNAME and password == VIEW_PASSWORD:
            st.session_state.logged_in = True
            st.session_state.role = "viewer"
            st.success("查看模式登录成功")
            st.rerun()
        else:
            st.error("用户名或密码错误")

def logout():
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.selected_sample_id = None
    st.rerun()

# ========= 主程序 =========
init_db()

if not st.session_state.logged_in:
    login_page()
    st.stop()

st.sidebar.title("导航")
st.sidebar.write(f"当前身份：{st.session_state.role}")

if st.sidebar.button("退出登录"):
    logout()

menu = ["数据查询", "指标对比", "样品对比"]

if st.session_state.role == "admin":
    menu.insert(0, "数据管理")
    menu.insert(0, "数据录入")
    menu.insert(2, "数据备份")

choice = st.sidebar.selectbox("选择功能", menu)

# ========= 数据录入 =========
if choice == "数据录入" and st.session_state.role == "admin":
    st.title("录入检测结果")

    _pending = st.session_state.get("pending_data")
    if _pending:
        st.warning(f"样品编号「{_pending.get('sample_id')}」在库中已存在。请选择：覆盖原数据，"
                   "或取消后修改样品编号重新录入。")
        _c1, _c2 = st.columns(2)
        with _c1:
            if st.button("覆盖原数据", key="btn_overwrite"):
                overwrite_sample(_pending)
                st.session_state.pop("pending_data", None)
        with _c2:
            if st.button("取消，重新输入", key="btn_cancel_dup"):
                st.session_state.pop("pending_data", None)
                st.info("已取消，原数据保持不变。请修改样品编号后重新填写。")

    with st.form("add_form"):
        sample_id = st.text_input("样品编号")
        product_type = st.selectbox(
            "产品类型",
            ["电池级磷酸锂", "电池级磷酸二氢锂", "其他"],
        )
        process_route = st.text_input("工艺路线（选填）")
        test_date = st.date_input("检测日期")
        tester = st.text_input("实验人员（选填）")
        remark = st.text_area("备注（选填）", placeholder="建议注明原料、实验方法等关键参数，便于关键词搜索")

        st.info("填写说明：下面每个指标都可以不填。**留空就代表「未检测」**，不会被当成 0。"
                "产品类型为「电池级磷酸锂」或「电池级磷酸二氢锂」时，会把各项指标逐条与对应产品类型看板固定标准自动对比（达标/不达标/未检测）；"
                "某指标若在该产品类型暂无对应标准，「是否达标」将显示「暂无标准」；"
                "选择「其他」时，因目前缺少对应看板数据，不做达标对比；"
                "锂收率 = 产物中锂质量 ÷（原料锂质量＋添加锂质量），磷收率 = 产物中磷质量 ÷（原料磷质量＋添加磷质量），"
                "均由程序自动算出，无需手动填写。质量指标看板固定在代码 STANDARD_INDICATORS 中，要改指标只能改代码。")

        indicator_values = {}
        mass_values = {}

        st.subheader("检测指标 - 基础项")
        for _field, _label, _unit in BASIC_FIELDS:
            indicator_values[_field] = metric_input(_field, _label, _unit)

        st.subheader("检测指标 - 质量看板新增项")
        for _field, _label, _unit in BOARD_EXTRA_FIELDS:
            indicator_values[_field] = metric_input(_field, _label, _unit)

        st.subheader("检测指标 - 新增项（钴 / pH / Li比 / 磁性异物）")
        st.caption("所有杂质指标已统一为%单位（1% = 10000ppm），磷酸锂与磷酸二氢锂共用同一录入框，保存时按各自产品类型看板自动判定。")
        for _field, _label, _unit in NEW_INPUT_FIELDS:
            indicator_values[_field] = metric_input(_field, _label, _unit)

        st.subheader("收率计算相关数据")
        st.caption("这几项同样可以留空；填了才会自动计算锂/磷收率。")
        for _field, _label, _unit in MASS_FIELDS:
            mass_values[_field] = metric_input(_field, _label, _unit)

        submitted = st.form_submit_button("保存数据")

        if submitted:
            if not sample_id:
                st.error("样品编号不能为空")
            else:
                _data = {
                    "sample_id": sample_id,
                    "product_type": product_type,
                    "process_route": process_route,
                    "batch_number": "",
                    "test_date": str(test_date),
                    "tester": tester,
                    "remark": remark,
                    **indicator_values,
                    **mass_values,
                }
                if sample_exists(sample_id):
                    st.session_state["pending_data"] = _data
                    st.rerun()
                else:
                    add_sample_and_result(_data)

# ========= 数据管理（删除数据） =========
elif choice == "数据管理" and st.session_state.role == "admin":
    st.title("数据管理 / 删除数据")

    st.warning("删除后不可恢复，请谨慎操作。删除会同时移除该样品的检测结果与样品信息。")

    ids_df = list_sample_ids()
    if ids_df.empty:
        st.info("当前数据库里还没有任何样品数据。")
    else:
        st.write(f"当前共有 {len(ids_df)} 个样品。")
        st.dataframe(ids_df, use_container_width=True)

        st.subheader("按样品编号删除（需二次确认）")
        target = st.selectbox("选择要删除的样品编号", ids_df["sample_id"].tolist(),
                              key="del_select")
        c1, c2 = st.columns([1, 3])
        with c1:
            confirm = st.checkbox("我已确认删除", key="del_confirm")
        with c2:
            if st.button("确认删除该样品", disabled=not confirm, key="btn_del"):
                if delete_sample(target):
                    st.success(f"已删除样品：{target}")
                    st.rerun()


# ========= 数据备份（导入导出） =========
elif choice == "数据备份" and st.session_state.role == "admin":
    st.title("数据备份 / 恢复")
    st.caption("更新代码、重新部署前后，用这里先把数据导出、再导回来。"
               "导入是覆盖式：会先清空当前数据，再按上传文件恢复。")
    tab_exp, tab_imp = st.tabs(["导出备份", "导入恢复"])
    with tab_exp:
        st.write("下载当前全部样品与检测结果的 Excel 备份文件。")
        _data_bytes, _ns, _nr = _export_backup_bytes()
        _fname = "lab_data_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
        st.download_button(
            label=f"下载 Excel 备份（{_ns} 个样品 / {_nr} 条结果）",
            data=_data_bytes,
            file_name=_fname,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with tab_imp:
        st.warning("导入会先清空当前所有数据，再按上传文件恢复。"
                   "请仅在重新部署后、确认已导出旧数据时使用。")
        _up = st.file_uploader("上传之前导出的 .xlsx 备份文件", type=["xlsx"], key="import_backup")
        _ok = st.checkbox("我已确认：导入将覆盖当前数据", key="imp_confirm")
        if _up is not None and st.button("确认导入并覆盖", disabled=not _ok, key="btn_import"):
            try:
                _ns2, _nr2 = _import_backup_bytes(_up)
                st.success(f"导入完成：已恢复 {_ns2} 个样品、{_nr2} 条检测结果。")
            except Exception as e:
                st.error(f"导入失败：{e}")

# ========= 数据查询 =========
elif choice == "数据查询":
    st.title("数据查询")

    # --- 按样品编号查询（可直接勾选已录入编号，支持多选） ---
    st.subheader("按样品编号查询")
    _q_all_df = list_sample_ids()
    _q_all_ids = _q_all_df["sample_id"].tolist() if not _q_all_df.empty else []

    q_ids = st.multiselect(
        "选择已录入的样品编号（支持多选，可输入关键字快速筛选）",
        options=_q_all_ids,
        default=[],
        placeholder="点击选择已录入的样品编号…",
        key="query_sample_ids",
    )
    q_extra_text = st.text_input(
        "也可手动补充输入编号（逗号分隔，可与上方选择合并；通常无需填写）",
        placeholder="例如：S20261020-01,S20261020-02",
        key="query_sample_extra",
    )
    q_extra_ids = [x.strip() for x in q_extra_text.split(",") if x.strip()]
    q_merged_ids = [s for s in dict.fromkeys(list(q_ids) + q_extra_ids) if s]

    if q_merged_ids:
        st.caption("已选择 " + str(len(q_merged_ids)) + " 个样品：" + "、".join(q_merged_ids))

    if st.button("查询样品", key="btn_query_sample"):
        if not q_merged_ids:
            st.warning("请勾选或输入至少一个样品编号")
        else:
            _not_found = []
            for _sid in q_merged_ids:
                _df = query_by_sample_id(_sid)
                if _df.empty:
                    _not_found.append(_sid)
                    continue
                st.markdown("#### 样品详情：" + str(_sid))
                render_sample_detail(_df)
                st.write("")
            if _not_found:
                st.warning("以下编号在库中未找到：" + "、".join(_not_found))

    # --- 组合筛选条件：产品类型 / 实验人员 / 备注，可任选一个或几个 ---
    st.subheader("组合筛选")
    st.caption("产品类型、实验人员、备注三项可任选其一或多于一同填写；填写的条件会同时生效(且关系)逐步缩小范围。留空的条件自动忽略。")
    fc1, fc2 = st.columns(2)
    with fc1:
        filter_product_type = st.selectbox(
            "产品类型筛选",
            ["全部类型", "电池级磷酸锂", "电池级磷酸二氢锂", "其他"],
            key="filter_product_type",
        )
    with fc2:
        filter_tester = st.text_input(
            "实验人员(支持模糊匹配)",
            key="filter_tester",
            placeholder="如：张三",
        )
    filter_sample_ids = st.multiselect(
        "样品编号筛选（可直接勾选已录入编号，支持多选）",
        options=_q_all_ids,
        default=[],
        placeholder="点击勾选要筛选的样品编号…",
        key="filter_sample_ids",
    )
    remark_keyword = st.text_input("备注关键词", key="search_remark",
                                   placeholder="如：球磨、原料配比…")

    active = []
    if filter_product_type != "全部类型":
        active.append(f"产品类型={filter_product_type}")
    if filter_tester:
        active.append(f"实验人员含「{filter_tester}」")
    if filter_sample_ids:
        active.append(f"样品编号({len(filter_sample_ids)}个)")
    if remark_keyword:
        active.append(f"备注含「{remark_keyword}」")
    if active:
        st.caption("当前筛选条件：" + "  且  ".join(active))

    if st.button("搜索", key="btn_search_remark"):
        if not active:
            st.warning("请至少填写一个筛选条件(产品类型 / 实验人员 / 样品编号 / 备注)")
        else:
            results = search_samples(filter_product_type, filter_tester, remark_keyword)
            if filter_sample_ids:
                results = results[results["sample_id"].isin(filter_sample_ids)]
            if results.empty:
                st.warning("未找到符合条件的样品")
            else:
                st.success(f"找到 {len(results)} 条结果")
                _slim_cols = [c for c in ["sample_id", "product_type", "tester", "test_date", "batch_number",
                                          "li_recovery", "p_recovery"] if c in results.columns]
                _st_dataframe(results[_slim_cols].copy(), width="stretch")
                st.caption("点击下方「查看详情」可查看该样品纵向的逐项指标与达标情况。")

                st.markdown("#### 点击查看详情")
                for idx, row in results.iterrows():
                    sid = row["sample_id"]
                    remark_text = row["remark"] if pd.notna(row["remark"]) else "无备注"
                    test_dt = row["test_date"]
                    li_rec = f"{row['li_recovery']}%" if pd.notna(row.get("li_recovery")) else "未计算"
                    p_rec = f"{row['p_recovery']}%" if pd.notna(row.get("p_recovery")) else "未计算"

                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**{sid}** | {test_dt} | 备注：{remark_text} | 锂收率：{li_rec} | 磷收率：{p_rec}")
                    with col2:
                        if st.button("查看详情", key=f"detail_{sid}"):
                            st.session_state.selected_sample_id = sid
                            st.rerun()

    # --- 查看选中样品的完整数据 ---
    if st.session_state.selected_sample_id:
        st.subheader(f"样品详情：{st.session_state.selected_sample_id}")
        detail_df = query_by_sample_id(st.session_state.selected_sample_id)
        if not detail_df.empty:
            render_sample_detail(detail_df)
        if st.button("关闭详情", key="close_detail"):
            st.session_state.selected_sample_id = None
            st.rerun()

    # --- 全部数据 ---
    st.subheader("全部数据（指标纵向呈现，每个样品一列）")
    # --- 全部数据（应用产品类型筛选） ---
    all_df = query_all_results()
    if filter_product_type and filter_product_type != "全部类型":
        all_df = all_df[all_df["product_type"] == filter_product_type]
    if filter_tester:
        all_df = all_df[all_df["tester"].astype(str).str.contains(filter_tester, na=False, regex=False)]
    if filter_sample_ids:
        all_df = all_df[all_df["sample_id"].isin(filter_sample_ids)]
    if remark_keyword:
        all_df = all_df[all_df["remark"].astype(str).str.contains(remark_keyword, na=False, regex=False)]
    render_results_vertical(all_df)

# ========= 指标对比 =========
elif choice == "指标对比":
    st.title("与指标对比（质量指标看板）")

    _cmp_all_df = list_sample_ids()
    _cmp_all_ids = _cmp_all_df["sample_id"].tolist() if not _cmp_all_df.empty else []

    cmp_ids = st.multiselect(
        "选择已录入的样品编号（支持多选，可输入关键字快速筛选）",
        options=_cmp_all_ids,
        default=[],
        placeholder="点击选择已录入的样品编号…",
        key="cmp_sample_ids",
    )
    cmp_extra_text = st.text_input(
        "也可手动补充输入编号（逗号分隔，可与上方选择合并；通常无需填写）",
        placeholder="例如：S20261020-01,S20261020-02",
        key="cmp_sample_extra",
    )
    cmp_extra_ids = [x.strip() for x in cmp_extra_text.split(",") if x.strip()]
    cmp_merged_ids = [s for s in dict.fromkeys(list(cmp_ids) + cmp_extra_ids) if s]

    st.info("以下标准范围来源于「金昌实验路线图」中的质量指标看板，可直接对照使用。")

    if st.button("开始对比", key="btn_compare"):
        if not cmp_merged_ids:
            st.warning("请勾选或输入至少一个样品编号")
        else:
            _cmp_not_found = []
            for _sid in cmp_merged_ids:
                _df = query_by_sample_id(_sid)
                if _df.empty:
                    _cmp_not_found.append(_sid)
                    continue
                st.markdown("#### 对比样品：" + str(_sid))
                compare_with_standard(_df)
                st.write("")
            if _cmp_not_found:
                st.warning("以下编号在库中未找到：" + "、".join(_cmp_not_found))

# ========= 样品对比 =========
elif choice == "样品对比":
    st.title("样品间整体对比")
    st.caption("无需选择对比指标，所选样品会逐项并排展示所有检测指标，直观对比整体差异。")

    _all_df = list_sample_ids()
    _all_ids = _all_df["sample_id"].tolist() if not _all_df.empty else []

    if not _all_ids:
        st.info("当前还没有已录入的样品数据，请先在「数据录入」中录入样品。")
    else:
        chosen_ids = st.multiselect(
            "选择要对比的样品（支持多选，可输入关键字快速筛选）",
            options=_all_ids,
            default=[],
            placeholder="点击选择已录入的样品编号…",
        )

        extra_text = st.text_input(
            "也可手动补充输入编号（逗号分隔，可与上方选择合并；通常无需填写）",
            placeholder="例如：S20261020-01,S20261020-02",
        )
        extra_ids = [x.strip() for x in extra_text.split(",") if x.strip()]

        merged_ids = [s for s in dict.fromkeys(list(chosen_ids) + extra_ids) if s]

        if len(merged_ids) >= 2:
            st.info("已选择 " + str(len(merged_ids)) + " 个样品：" + "、".join(merged_ids))
        elif len(merged_ids) == 1:
            st.info("已选择 1 个样品：" + merged_ids[0] + "（选择 2 个及以上对比更直观）")

        if st.button("对比样品", key="btn_compare_samples"):
            if not merged_ids:
                st.warning("请至少选择或输入一个样品编号")
            else:
                compare_samples(merged_ids)
