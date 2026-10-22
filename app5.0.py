import sqlite3
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

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
# 格式: (数据库字段名, 显示名称, 单位, 标准下限, 标准上限, 比较类型)
# 比较类型: "gte"(>=), "lte"(<=), "eq"(=)
STANDARD_INDICATORS = [
    ("d50", "粒径(D50)", "", None, 50, "lte"),
    ("li_content", "Li", "%", 17.8, None, "gte"),
    ("p_content", "P", "%", 26.5, None, "gte"),
    ("purity_content", "含量", "%", 99.0, None, "gte"),
    ("moisture", "水分", "%", None, 0.4, "lte"),
    ("so4_content", "SO4", "%", None, 0.15, "lte"),
    ("cl_content", "Cl", "ppm", None, 100, "lte"),
    ("na_content", "Na", "ppm", None, 250, "lte"),
    ("k_content", "K", "ppm", None, 50, "lte"),
    ("ca_content", "Ca", "ppm", None, 100, "lte"),
    ("mn_content", "Mn", "ppm", None, 10, "lte"),
    ("ni_content", "Ni", "ppm", None, 20, "lte"),
    ("cu_content", "Cu", "ppm", None, 10, "lte"),
    ("pb_content", "Pb", "ppm", None, 10, "lte"),
    ("zn_content", "Zn", "ppm", None, 10, "lte"),
    ("cr_content", "Cr", "ppm", None, 20, "lte"),
    ("mg_content", "Mg", "ppm", None, 100, "lte"),
    ("fe_content", "Fe", "ppm", None, 50, "lte"),
    ("al_content", "Al", "ppm", None, 20, "lte"),
    ("b_content", "B", "ppm", None, 100, "lte"),
    ("magnetic_content", "磁性物", "ppm", None, 1, "lte"),
    ("magnetic_particles", "磁性金属颗粒", "Pcs/kg", None, 200, "lte"),
    ("cu_zn_particles", "Cu/Zn颗粒", "Pcs/kg", 0, 0, "eq"),
]

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
    return True


def evaluate_standard(values):
    """自动达标判定：已检测项全部达标->达标；任一项超标->不达标；全未检测->未判定"""
    checked = 0
    failed = []
    for key, name, unit, low, high, cmp_type in STANDARD_INDICATORS:
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
    ("na_content", "钠含量 Na", "ppm"),
    ("ca_content", "钙含量 Ca", "ppm"),
    ("mg_content", "镁含量 Mg", "ppm"),
    ("b_content", "硼含量 B", "ppm"),
    ("si_content", "硅含量 Si", "ppm"),
    ("cl_content", "氯离子 Cl", "ppm"),
    ("al_content", "铝含量 Al", "ppm"),
    ("fe_content", "铁含量 Fe", "ppm"),
    ("co3_content", "碳酸根 CO3", "ppm"),
    ("so4_content", "硫酸根 SO4", "%"),
    ("moisture", "含水量/水分", "%"),
]

BOARD_EXTRA_FIELDS = [
    ("k_content", "钾含量 K", "ppm"),
    ("mn_content", "锰含量 Mn", "ppm"),
    ("ni_content", "镍含量 Ni", "ppm"),
    ("cu_content", "铜含量 Cu", "ppm"),
    ("pb_content", "铅含量 Pb", "ppm"),
    ("zn_content", "锌含量 Zn", "ppm"),
    ("cr_content", "铬含量 Cr", "ppm"),
    ("magnetic_content", "磁性物", "ppm"),
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


# ========= 数据库初始化 =========
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
    ]

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
        + [f for f, _, _ in MASS_FIELDS]
    )
    label_map = {f: lbl for f, lbl, _ in (BASIC_FIELDS + BOARD_EXTRA_FIELDS + MASS_FIELDS)}

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
            data["sample_id"],
            data["product_type"],
            data["process_route"],
            data["batch_number"],
            data["test_date"],
            data["tester"],
            data["remark"],
        ))

        grade, grade_failed = evaluate_standard(data)
        data["standard_grade"] = grade
        li_recovery, p_recovery = calculate_recovery(
            data.get("product_li_mass"),
            data.get("product_p_mass"),
            data["raw_li_mass"],
            data["raw_p_mass"],
            data["added_li_mass"],
            data["added_p_mass"],
        )

        cursor.execute("""
            INSERT INTO test_results
            (sample_id,
             li_content, p_content, na_content, ca_content, mg_content,
             b_content, si_content, cl_content, al_content, fe_content,
             co3_content, so4_content, moisture,
             k_content, mn_content, ni_content, cu_content, pb_content,
             zn_content, cr_content, magnetic_content, magnetic_particles,
             cu_zn_particles, d50, purity_content,
             raw_li_mass, raw_p_mass, added_li_mass, added_p_mass,
             product_li_mass, product_p_mass,
             li_recovery, p_recovery, standard_grade)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["sample_id"],
            data["li_content"],
            data["p_content"],
            data["na_content"],
            data["ca_content"],
            data["mg_content"],
            data["b_content"],
            data["si_content"],
            data["cl_content"],
            data["al_content"],
            data["fe_content"],
            data["co3_content"],
            data["so4_content"],
            data["moisture"],
            data.get("k_content"),
            data.get("mn_content"),
            data.get("ni_content"),
            data.get("cu_content"),
            data.get("pb_content"),
            data.get("zn_content"),
            data.get("cr_content"),
            data.get("magnetic_content"),
            data.get("magnetic_particles"),
            data.get("cu_zn_particles"),
            data.get("d50"),
            data.get("purity_content"),
            data["raw_li_mass"],
            data["raw_p_mass"],
            data["added_li_mass"],
            data["added_p_mass"],
            data.get("product_li_mass"),
            data.get("product_p_mass"),
            li_recovery,
            p_recovery,
            data["standard_grade"],
        ))

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
    df = pd.read_sql_query("""
        SELECT s.sample_id,
               s.product_type,
               s.process_route,
               s.batch_number,
               s.test_date,
               s.tester,
               s.remark,
               r.li_content,
               r.p_content,
               r.na_content,
               r.ca_content,
               r.mg_content,
               r.b_content,
               r.si_content,
               r.cl_content,
               r.al_content,
               r.fe_content,
               r.co3_content,
               r.so4_content,
               r.moisture,
               r.k_content,
               r.mn_content,
               r.ni_content,
               r.cu_content,
               r.pb_content,
               r.zn_content,
               r.cr_content,
               r.magnetic_content,
               r.magnetic_particles,
               r.cu_zn_particles,
               r.d50,
               r.purity_content,
               r.raw_li_mass,
               r.raw_p_mass,
               r.added_li_mass,
               r.added_p_mass,
               r.product_li_mass,
               r.product_p_mass,
               r.li_recovery,
               r.p_recovery,
               r.standard_grade
        FROM samples s
        LEFT JOIN test_results r ON s.sample_id = r.sample_id
        WHERE s.sample_id = ?
    """, conn, params=(sample_id,))
    conn.close()
    return df

def query_all_results():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT s.sample_id,
               s.product_type,
               s.process_route,
               s.batch_number,
               s.test_date,
               s.tester,
               s.remark,
               r.li_content,
               r.p_content,
               r.na_content,
               r.ca_content,
               r.mg_content,
               r.b_content,
               r.si_content,
               r.cl_content,
               r.al_content,
               r.fe_content,
               r.co3_content,
               r.so4_content,
               r.moisture,
               r.k_content,
               r.mn_content,
               r.ni_content,
               r.cu_content,
               r.pb_content,
               r.zn_content,
               r.cr_content,
               r.magnetic_content,
               r.magnetic_particles,
               r.cu_zn_particles,
               r.d50,
               r.purity_content,
               r.li_recovery,
               r.p_recovery,
               r.standard_grade
        FROM samples s
        LEFT JOIN test_results r ON s.sample_id = r.sample_id
        ORDER BY s.test_date DESC
    """, conn)
    conn.close()
    return df

def search_by_remark(keyword):
    """按备注关键词模糊搜索"""
    conn = sqlite3.connect(DB_PATH)
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
    st.subheader("质量指标看板 - 对比结果")

    compare_data = []

    for key, name, unit, low, high, cmp_type in STANDARD_INDICATORS:
        value = row.get(key)

        if pd.isna(value):
            status = NOT_TESTED_TEXT
        elif check_indicator(value, low, high, cmp_type):
            status = "达标"
        else:
            status = "不达标"

        compare_data.append({
            "指标": name,
            "实测值": (NOT_TESTED_TEXT if pd.isna(value) else f"{value}{unit}"),
            "标准范围": standard_range_text(unit, low, high, cmp_type),
            "是否达标": status,
        })

    _st_dataframe(pd.DataFrame(compare_data), width="stretch")

def _is_null(v):
    return v is None or (isinstance(v, float) and pd.isna(v))


def render_sample_detail(df):
    """单样品纵向详情：基本信息 + 逐项指标达标 + 收率数据，仿照「指标对比」竖排呈现"""
    if df.empty:
        st.warning("没有查询到数据")
        return
    row = df.iloc[0]

    def g(key):
        v = row.get(key)
        return "" if _is_null(v) else v

    info_pairs = [
        ("样品编号", g("sample_id")),
        ("产品类型", g("product_type")),
        ("工艺路线", g("process_route")),
        ("批次号", g("batch_number")),
        ("检测日期", g("test_date")),
        ("检测人员", g("tester")),
        ("备注", g("remark")),
    ]
    st.subheader("基本信息")
    _st_dataframe(pd.DataFrame({"项目": [p[0] for p in info_pairs],
                                "内容": [p[1] for p in info_pairs]}), width="stretch")

    st.subheader("检测指标（逐项对照看板固定标准）")
    rows = []
    for key, name, unit, low, high, cmp_type in STANDARD_INDICATORS:
        v = row.get(key)
        rows.append({
            "指标": name,
            "实测值": (NOT_TESTED_TEXT if _is_null(v) else f"{fmt_display(v)}{unit}"),
            "标准范围": standard_range_text(unit, low, high, cmp_type),
            "是否达标": _item_status(v, low, high, cmp_type),
        })
    _st_dataframe(pd.DataFrame(rows), width="stretch")

    st.subheader("收率计算数据")
    rec_pairs = [
        ("原料锂质量(g)", g("raw_li_mass")),
        ("添加锂质量(g)", g("added_li_mass")),
        ("产物中锂质量(g)", g("product_li_mass")),
        ("锂收率", "" if _is_null(row.get("li_recovery")) else f"{fmt_display(row.get('li_recovery'))}%"),
        ("原料磷质量(g)", g("raw_p_mass")),
        ("添加磷质量(g)", g("added_p_mass")),
        ("产物中磷质量(g)", g("product_p_mass")),
        ("磷收率", "" if _is_null(row.get("p_recovery")) else f"{fmt_display(row.get('p_recovery'))}%"),
    ]
    _st_dataframe(pd.DataFrame({"项目": [p[0] for p in rec_pairs],
                                "数值": [p[1] for p in rec_pairs]}), width="stretch")


def render_results_vertical(df):
    """多样品结果：指标为行、样品编号为列，纵向呈现，避免横向拖动进度条"""
    if df.empty:
        st.warning("没有可展示的数据")
        return
    df = df.copy()
    if "standard_grade" in df.columns:
        df = df.drop(columns=["standard_grade"])

    sids = [str(s) for s in df["sample_id"].tolist()]
    n = len(df)

    def col_of(key):
        return [df.iloc[i].get(key) for i in range(n)]

    row_items = []
    for label, key in [("产品类型", "product_type"), ("工艺路线", "process_route"),
                       ("批次号", "batch_number"), ("检测日期", "test_date"),
                       ("检测人员", "tester"), ("备注", "remark")]:
        if key in df.columns:
            vals = col_of(key)
            row_items.append((label, [("" if _is_null(v) else fmt_display(v)) for v in vals]))

    for key, name, unit, low, high, cmp_type in STANDARD_INDICATORS:
        if key in df.columns:
            vals = col_of(key)
            row_items.append(((f"{name}({unit})" if unit else name) + "·实测",
                              [(NOT_TESTED_TEXT if _is_null(v) else f"{fmt_display(v)}{unit}") for v in vals]))
            row_items.append((f"{name}·是否达标",
                              [_item_status(v, low, high, cmp_type) for v in vals]))

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


# ========= 样品间对比 =========
def compare_samples(sample_ids, element):
    if not sample_ids:
        st.warning("请至少输入一个样品编号")
        return

    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join(["?"] * len(sample_ids))
    df = pd.read_sql_query(
        f"SELECT sample_id, {element} FROM test_results WHERE sample_id IN ({placeholders})",
        conn,
        params=sample_ids,
    )
    conn.close()

    if df.empty:
        st.warning("未找到对比数据")
        return

    _st_dataframe(df, width="stretch")

    fig, ax = plt.subplots()
    ax.bar(df["sample_id"].astype(str), df[element])
    ax.set_title(f"{element} 样品对比")
    ax.set_xlabel("样品编号")
    ax.set_ylabel(element)
    plt.xticks(rotation=45)
    st.pyplot(fig)

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
        process_route = st.text_input("工艺路线")
        batch_number = st.text_input("批次号")
        test_date = st.date_input("检测日期")
        tester = st.text_input("检测人员")
        remark = st.text_area("备注")

        st.info("填写说明：下面每个指标都可以不填。**留空就代表「未检测」**，不会被当成 0。"
                "达标情况会按每一项指标逐条与看板固定标准自动对比（达标/不达标/未检测），不再做整体判定；"
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
                    "batch_number": batch_number,
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

# ========= 数据查询 =========
elif choice == "数据查询":
    st.title("数据查询")

    # --- 按样品编号查询 ---
    st.subheader("按样品编号查询")
    sample_id = st.text_input("输入样品编号", key="query_sample_id")

    if st.button("查询样品", key="btn_query_sample"):
        if not sample_id:
            st.warning("请输入样品编号")
        else:
            df = query_by_sample_id(sample_id)
            if df.empty:
                st.warning("未找到该样品数据")
            else:
                render_sample_detail(df)

    # --- 按备注关键词搜索 ---
    st.subheader("按备注关键词搜索")
    remark_keyword = st.text_input("输入备注中的关键词", key="search_remark")

    if st.button("搜索备注", key="btn_search_remark"):
        if not remark_keyword:
            st.warning("请输入关键词")
        else:
            results = search_by_remark(remark_keyword)
            if results.empty:
                st.warning(f"未找到备注中包含「{remark_keyword}」的样品")
            else:
                st.success(f"找到 {len(results)} 条结果")
                _slim_cols = [c for c in ["sample_id", "test_date", "batch_number",
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
    render_results_vertical(query_all_results())

# ========= 指标对比 =========
elif choice == "指标对比":
    st.title("与指标对比（质量指标看板）")

    sample_id = st.text_input("样品编号")

    st.info("以下标准范围来源于「金昌实验路线图」中的质量指标看板，可直接对照使用。")

    if st.button("开始对比", key="btn_compare"):
        if not sample_id:
            st.warning("请输入样品编号")
        else:
            df = query_by_sample_id(sample_id)
            compare_with_standard(df)

# ========= 样品对比 =========
elif choice == "样品对比":
    st.title("样品间对比")

    sample_ids_text = st.text_input(
        "输入多个样品编号，用逗号分隔",
        placeholder="例如：S20261020-01,S20261020-02,S20261020-03",
    )

    element = st.selectbox(
        "选择对比指标",
        [
            "li_content",
            "p_content",
            "na_content",
            "ca_content",
            "mg_content",
            "b_content",
            "si_content",
            "cl_content",
            "al_content",
            "fe_content",
            "co3_content",
            "so4_content",
            "moisture",
            "k_content",
            "mn_content",
            "ni_content",
            "cu_content",
            "pb_content",
            "zn_content",
            "cr_content",
            "magnetic_content",
            "magnetic_particles",
            "cu_zn_particles",
            "d50",
            "purity_content",
            "li_recovery",
            "p_recovery",
        ],
    )

    if st.button("对比样品"):
        if not sample_ids_text:
            st.warning("请输入样品编号")
        else:
            ids = [x.strip() for x in sample_ids_text.split(",") if x.strip()]
            if not ids:
                st.warning("请输入有效的样品编号")
            else:
                compare_samples(ids, element)
