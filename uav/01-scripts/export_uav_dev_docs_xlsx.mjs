import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, "..", "..");
const OUT_ROOT = path.join(ROOT, "docs");

const payloadPath = process.argv[2];
if (!payloadPath) {
  throw new Error("missing export payload path");
}

const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));

function colLetter(index) {
  let value = index;
  let out = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    out = String.fromCharCode(65 + remainder) + out;
    value = Math.floor((value - 1) / 26);
  }
  return out;
}

function cell(row, col) {
  return `${colLetter(col)}${row}`;
}

function rangeA1(startRow, startCol, numRows, numCols) {
  return `${cell(startRow, startCol)}:${cell(startRow + numRows - 1, startCol + numCols - 1)}`;
}

function writeMatrix(sheet, startRow, startCol, matrix) {
  if (!matrix.length || !matrix[0].length) return;
  sheet.getRange(rangeA1(startRow, startCol, matrix.length, matrix[0].length)).values = matrix;
}

function setColumnWidths(sheet, widths) {
  widths.forEach((width, index) => {
    sheet.getRange(`${colLetter(index + 1)}:${colLetter(index + 1)}`).format.columnWidthPx = width;
  });
}

function styleTitle(sheet, title, subtitle, cols) {
  const titleRange = sheet.getRange(rangeA1(1, 1, 1, cols));
  titleRange.values = [[title, ...Array(cols - 1).fill(null)]];
  titleRange.format.fill = {
    type: "solid",
    color: { type: "theme", value: "accent1", transform: { darken: 5 } },
  };
  titleRange.format.font = { color: "lt1", bold: true, size: 16 };

  const subtitleRange = sheet.getRange(rangeA1(2, 1, 1, cols));
  subtitleRange.values = [[subtitle, ...Array(cols - 1).fill(null)]];
  subtitleRange.format.wrapText = true;
  subtitleRange.format.font = { color: "#444444", size: 11 };
}

function styleSectionTitle(sheet, row, cols) {
  const range = sheet.getRange(rangeA1(row, 1, 1, cols));
  range.format.fill = {
    type: "solid",
    color: { type: "theme", value: "accent2", transform: { lighten: 35 } },
  };
  range.format.font = { bold: true, size: 13 };
}

function styleHeader(sheet, row, cols) {
  const range = sheet.getRange(rangeA1(row, 1, 1, cols));
  range.format.fill = "accent1";
  range.format.font = { color: "lt1", bold: true, size: 11 };
  range.format.wrapText = true;
}

function styleBody(sheet, startRow, rows, cols) {
  if (rows <= 0) return;
  const range = sheet.getRange(rangeA1(startRow, 1, rows, cols));
  range.format.wrapText = true;
  range.format.borders = { preset: "outside", style: "thin", color: "#D9D9D9" };
}

function writeSection(sheet, startRow, title, headers, rows, widths) {
  const cols = headers.length;
  const titleMatrix = [[title, ...Array(cols - 1).fill(null)]];
  writeMatrix(sheet, startRow, 1, titleMatrix);
  styleSectionTitle(sheet, startRow, cols);

  writeMatrix(sheet, startRow + 1, 1, [headers]);
  styleHeader(sheet, startRow + 1, cols);

  if (rows.length) {
    writeMatrix(sheet, startRow + 2, 1, rows);
    styleBody(sheet, startRow + 2, rows.length, cols);
  }

  setColumnWidths(sheet, widths);
  return startRow + rows.length + 4;
}

function createInterfaceWorkbook(rows) {
  const workbook = Workbook.create();
  const byName = new Map(rows.map((row) => [row.name, row]));
  const byCategory = (category) => rows.filter((row) => row.category === category);

  const guideSheet = workbook.worksheets.add("怎么用");
  setColumnWidths(guideSheet, [210, 220, 360]);
  styleTitle(
    guideSheet,
    "非凸α接口总表怎么用",
    "这份表不是让你逐行背。先看“推荐接入”，再按任务去看状态接口、动作接口、脚本入口、参数入口和 RC 映射，最后才看完整原表。",
    3,
  );

  let row = 4;
  row = writeSection(
    guideSheet,
    row,
    "先按你的问题去找 sheet",
    ["我现在要做什么", "先看哪个 sheet", "为什么"],
    [
      ["不想按类别读，想按任务场景直接找", "场景速查", "把日常最常见的开发和排查场景压成一张表，先看这里最快。"],
      ["判断上层系统先接哪些接口", "推荐接入", "这里把当前机器最值得先订阅和先发布的接口浓缩好了。"],
      ["看电量、状态、定位", "状态接口", "这是日常观测入口，先订阅这些再谈上层逻辑。"],
      ["触发起飞、开始任务、返程、降落", "动作接口", "这些是当前机器已经稳定落地的动作原语。"],
      ["搞清楚一键脚本到底起了什么", "脚本入口", "这里把 run_single_lio/vio 和动作脚本拆开写了。"],
      ["想改航点、起飞高度、规划参数", "参数入口", "这里告诉你该改哪个文件，不用翻整仓。"],
      ["想确认遥控器会不会打断软件", "RC映射", "RC 是最高优先级安全边界，这里单独列出。"],
      ["要追溯到原始事实", "完整原表", "保留全部字段，便于追源码和证据。"],
    ],
    [210, 220, 360],
  );

  writeSection(
    guideSheet,
    row,
    "给上层系统的最小闭环",
    ["目标", "推荐接口", "说明"],
    [
      ["状态订阅", "/mavros/state, /mavros/battery, /mavros/rc/in", "先拿到飞控、供电和 RC 安全门，别一上来就发控制。"],
      ["定位订阅", "/ekf/ekf_odom 或 /vins/imu_propagate", "LIO/VIO 二选一，根据当前启动链决定。"],
      ["动作发布", "/px4ctrl/takeoff_land, /move_base_simple/goal, /back_trigger", "这是当前机器最适合上层系统直接调用的动作层。"],
      ["先别碰", "/setpoints_cmd 和 px4ctrl 内部状态机", "这两层风险更高，不适合作为第一接入点。"],
    ],
    [210, 220, 360],
  );

  const recommendedSheet = workbook.worksheets.add("推荐接入");
  setColumnWidths(recommendedSheet, [180, 180, 110, 110, 220, 180, 260]);
  styleTitle(
    recommendedSheet,
    "推荐接入",
    "如果你要做二开，先围绕这 8 个接口建立闭环，不要第一步就下钻到控制器内部。",
    7,
  );
  const recommendedRows = [
    ["看飞控连接与模式", "/mavros/state"],
    ["看电量", "/mavros/battery"],
    ["看 RC 安全门", "/mavros/rc/in"],
    ["看 LIO 定位", "/ekf/ekf_odom"],
    ["看 VIO 定位", "/vins/imu_propagate"],
    ["触发起飞/降落", "/px4ctrl/takeoff_land"],
    ["触发开始任务", "/move_base_simple/goal"],
    ["触发返程", "/back_trigger"],
  ].map(([goal, name]) => {
    const raw = byName.get(name);
    return [
      goal,
      raw.name,
      raw.type,
      raw.direction,
      raw.typical_use,
      raw.preconditions,
      raw.risks,
    ];
  });
  writeSection(
    recommendedSheet,
    4,
    "建议你先围绕这些接口做开发",
    ["接入目标", "接口", "类型", "方向", "怎么用", "前置条件", "风险"],
    recommendedRows,
    [180, 180, 110, 110, 220, 180, 260],
  );
  recommendedSheet.freezePanes.freezeRows(5);

  const scenarioSheet = workbook.worksheets.add("场景速查");
  setColumnWidths(scenarioSheet, [150, 180, 240, 180, 260]);
  styleTitle(
    scenarioSheet,
    "场景速查",
    "如果你已经知道自己要做什么，就先从这一页进，不要先扎进完整原表。",
    5,
  );
  writeSection(
    scenarioSheet,
    4,
    "按场景找入口",
    ["场景", "先做什么", "关键接口/文件", "深挖去哪", "备注"],
    [
      [
        "看电量",
        "先确认 mavros 在线",
        "/mavros/battery",
        "状态接口",
        "最常用日常检查项，先看电压和 percentage。",
      ],
      [
        "看飞控状态",
        "先看连接、armed、mode",
        "/mavros/state",
        "状态接口",
        "起飞前和排障时都应先看它。",
      ],
      [
        "看定位是否正常",
        "按当前启动链选 LIO 或 VIO",
        "/ekf/ekf_odom 或 /vins/imu_propagate",
        "状态接口",
        "LIO/VIO 二选一，不要混着判断。",
      ],
      [
        "看 RC 会不会打断软件",
        "先看原始通道，再看通道含义",
        "/mavros/rc/in + RC Channel 5/6/7/8",
        "RC映射",
        "RC 是最高优先级安全边界。",
      ],
      [
        "触发起飞",
        "确认前置条件后再发动作",
        "/px4ctrl/takeoff_land 或 takeoff.sh",
        "动作接口 / 脚本入口",
        "takeoff_land_cmd=1；RC 档位不对时会被拒绝。",
      ],
      [
        "开始任务",
        "触发任务入口，不直接发底层控制",
        "/move_base_simple/goal 或 pub_trigger.sh",
        "动作接口 / 脚本入口",
        "当前多点任务最自然的开始入口。",
      ],
      [
        "返程",
        "走返程 trigger，不要直接猜返回点逻辑",
        "/back_trigger 或 back.sh",
        "动作接口 / 脚本入口",
        "具体返程点来自 points.yaml 里的 test_back。",
      ],
      [
        "降落",
        "优先用已有动作原语",
        "/px4ctrl/takeoff_land 或 land.sh",
        "动作接口 / 脚本入口",
        "takeoff_land_cmd=2；与起飞共用同一 topic。",
      ],
      [
        "改航点",
        "先改 YAML，再确认模式",
        "points.yaml + multipointplan_exp_lio.launch",
        "参数入口",
        "先确认 fligt_type，再按 test1~test4 格式改。",
      ],
      [
        "改起飞高度",
        "只改控制器参数，不要误改规划参数",
        "ctrl_param_fpv.yaml",
        "参数入口",
        "对应 auto_takeoff_land.takeoff_height。",
      ],
      [
        "接上层 Agent / MQTT",
        "先做状态订阅和动作发布闭环",
        "/mavros/state, /mavros/battery, /px4ctrl/takeoff_land, /move_base_simple/goal",
        "推荐接入",
        "第一刀不要碰 /setpoints_cmd 和 px4ctrl 状态机。",
      ],
    ],
    [150, 180, 240, 180, 260],
  );
  scenarioSheet.freezePanes.freezeRows(5);

  const statusSheet = workbook.worksheets.add("状态接口");
  setColumnWidths(statusSheet, [180, 180, 140, 160, 220, 220, 220, 120]);
  styleTitle(statusSheet, "状态接口", "日常观察先从这里开始。", 8);
  writeSection(
    statusSheet,
    4,
    "当前最常用的状态类接口",
    ["接口", "消息类型", "上游", "下游/使用者", "用途", "常用命令", "风险/备注", "当前状态"],
    byCategory("state").map((row) => [
      row.name,
      row.message_or_format,
      row.upstream,
      row.downstream,
      row.typical_use,
      row.example,
      row.risks,
      row.machine_status,
    ]),
    [180, 180, 140, 160, 220, 220, 220, 120],
  );
  statusSheet.freezePanes.freezeRows(5);

  const actionSheet = workbook.worksheets.add("动作接口");
  setColumnWidths(actionSheet, [180, 180, 120, 180, 200, 240, 240]);
  styleTitle(actionSheet, "动作接口", "这是当前机器最适合上层系统直接调用的动作原语层。", 7);
  writeSection(
    actionSheet,
    4,
    "动作接口",
    ["接口", "输入格式", "方向", "前置条件", "作用", "示例", "风险"],
    byCategory("action").map((row) => [
      row.name,
      row.message_or_format,
      row.direction,
      row.preconditions,
      row.typical_use,
      row.example,
      row.risks,
    ]),
    [180, 180, 120, 180, 200, 240, 240],
  );
  actionSheet.freezePanes.freezeRows(5);

  const scriptSheet = workbook.worksheets.add("脚本入口");
  setColumnWidths(scriptSheet, [180, 180, 260, 180, 220, 240]);
  styleTitle(scriptSheet, "脚本入口", "现场同事真实在用的是脚本入口，这里告诉你每个脚本大致负责什么。", 6);
  writeSection(
    scriptSheet,
    4,
    "脚本入口",
    ["脚本", "类型/格式", "关键内容", "前置条件", "典型用途", "风险"],
    byCategory("script").map((row) => [
      row.name,
      row.message_or_format,
      row.key_fields,
      row.preconditions,
      row.typical_use,
      row.risks,
    ]),
    [180, 180, 260, 180, 220, 240],
  );
  scriptSheet.freezePanes.freezeRows(5);

  const parameterSheet = workbook.worksheets.add("参数入口");
  setColumnWidths(parameterSheet, [200, 120, 220, 200, 220, 240]);
  styleTitle(parameterSheet, "参数入口", "如果你是来改行为，不是来重写系统，那先看这些文件。", 6);
  writeSection(
    parameterSheet,
    4,
    "参数入口",
    ["文件", "格式", "关键参数", "作用", "典型用法", "风险"],
    byCategory("parameter").map((row) => [
      row.name,
      row.message_or_format,
      row.key_fields,
      row.typical_use,
      row.example,
      row.risks,
    ]),
    [200, 120, 220, 200, 220, 240],
  );
  parameterSheet.freezePanes.freezeRows(5);

  const rcSheet = workbook.worksheets.add("RC映射");
  setColumnWidths(rcSheet, [180, 130, 220, 180, 200, 240]);
  styleTitle(rcSheet, "RC映射", "开发时一定要把 RC 当作安全边界，而不是背景信息。", 6);
  writeSection(
    rcSheet,
    4,
    "遥控器映射",
    ["通道", "输入类型", "含义", "下游", "典型用途", "风险"],
    byCategory("rc").map((row) => [
      row.name,
      row.message_or_format,
      row.key_fields,
      row.downstream,
      row.typical_use,
      row.risks,
    ]),
    [180, 130, 220, 180, 200, 240],
  );
  rcSheet.freezePanes.freezeRows(5);

  const rawSheet = workbook.worksheets.add("完整原表");
  const rawHeaders = [
    "id",
    "category",
    "name",
    "type",
    "direction",
    "message_or_format",
    "key_fields",
    "upstream",
    "downstream",
    "preconditions",
    "typical_use",
    "example",
    "machine_status",
    "risks",
    "evidence_id",
    "source_path",
  ];
  setColumnWidths(rawSheet, [80, 100, 180, 110, 120, 180, 180, 120, 120, 160, 180, 220, 110, 220, 120, 260]);
  styleTitle(rawSheet, "完整原表", "这里保留全部原始字段，用于追溯和查证。", rawHeaders.length);
  writeSection(
    rawSheet,
    4,
    "完整原表",
    rawHeaders,
    rows.map((row) => rawHeaders.map((header) => row[header] ?? "")),
    [80, 100, 180, 110, 120, 180, 180, 120, 120, 160, 180, 220, 110, 220, 120, 260],
  );
  rawSheet.freezePanes.freezeRows(5);

  return workbook;
}

function createFeatureWorkbook(rows) {
  const workbook = Workbook.create();
  const deployed = rows.filter((row) => row.onboard_deployed === "yes");
  const extension = rows.filter((row) => row.onboard_deployed !== "yes");

  const statusText = (row) => {
    if (row.onboard_deployed === "yes") return "当前已部署";
    if (row.repo_source_present === "partial") return "源码片段存在，但非实机主链";
    if (row.repo_source_present === "yes") return "源码存在，但未作为当前机上主链";
    return "产品线文档提到，但当前机上未落地";
  };

  const guideSheet = workbook.worksheets.add("怎么用");
  setColumnWidths(guideSheet, [220, 240, 360]);
  styleTitle(
    guideSheet,
    "功能部署矩阵怎么用",
    "你要先看“当前已部署”，那才是这台机器现在能直接接的能力；“扩展能力”只能当路线图或后续项目，不要混入当前默认链路。",
    3,
  );
  let row = 4;
  row = writeSection(
    guideSheet,
    row,
    "读表规则",
    ["判断问题", "看哪一列/哪一页", "解释"],
    [
      ["这个功能现在能不能直接接", "当前已部署", "只有 onboard_deployed=yes 的功能，才算当前机器已部署。"],
      ["这个功能为什么没进主文档", "扩展能力", "这里单列 Elastic/FUEL/Formation/YOLO 等非当前主链能力。"],
      ["我该怎么验证它真的活着", "完整矩阵中的 verification_method", "每行都保留了实际验证方法。"],
      ["我要追溯证据", "完整矩阵 + 证据索引", "需要回源码或知识库时，再看原始矩阵。"],
    ],
    [220, 240, 360],
  );
  writeSection(
    guideSheet,
    row,
    "当前机器的结论",
    ["结论", "含义", "对开发的影响"],
    [
      ["单机 LIO / VIO 是主链", "当前机器真的能跑的主路径", "二开优先围绕它们设计接口，不要被产品线文档带偏。"],
      ["Elastic / FUEL / Formation / YOLO 不是当前默认能力", "它们只能算扩展方向", "不要把这些能力写进当前日常使用和接口对接主流程。"],
      ["多点任务和自动起降已经落地", "当前上层系统有现成动作原语可接", "先把高层桥接建立起来，再考虑深改算法层。"],
    ],
    [220, 240, 360],
  );

  const deployedSheet = workbook.worksheets.add("当前已部署");
  setColumnWidths(deployedSheet, [160, 120, 220, 260, 220, 220]);
  styleTitle(deployedSheet, "当前已部署", "这里的功能才应该进入当前机器的速查和开发主路径。", 6);
  writeSection(
    deployedSheet,
    4,
    "当前已部署功能",
    ["功能", "可直接运行", "入口", "怎么验证", "硬件依赖", "备注"],
    deployed.map((row) => [
      row.feature_name,
      row.directly_runnable === "yes" ? "是" : "否",
      row.primary_entrypoint,
      row.verification_method,
      row.required_hardware,
      row.notes,
    ]),
    [160, 120, 220, 260, 220, 220],
  );
  deployedSheet.freezePanes.freezeRows(5);

  const extensionSheet = workbook.worksheets.add("扩展能力");
  setColumnWidths(extensionSheet, [180, 220, 220, 220, 220]);
  styleTitle(extensionSheet, "扩展能力", "这些能力可以作为后续路线图，但不该混入当前机器默认链路。", 5);
  writeSection(
    extensionSheet,
    4,
    "当前不应写入主路径的能力",
    ["功能", "当前状态", "为什么现在不算机上能力", "需要补什么", "入口/备注"],
    extension.map((row) => [
      row.feature_name,
      statusText(row),
      row.notes,
      row.required_hardware,
      row.primary_entrypoint,
    ]),
    [180, 220, 220, 220, 220],
  );
  extensionSheet.freezePanes.freezeRows(5);

  const adviceSheet = workbook.worksheets.add("二开建议");
  setColumnWidths(adviceSheet, [220, 320, 320]);
  styleTitle(adviceSheet, "二开建议", "这一页把“当前已部署”和“后续扩展”之间的边界讲明白。", 3);
  writeSection(
    adviceSheet,
    4,
    "建议按这个顺序做",
    ["开发目标", "建议", "不要这么做"],
    [
      ["接上层系统", "先围绕单机 LIO/VIO、状态观测、多点任务、自动起降建闭环。", "不要一开始就把 Elastic 或集群写成当前默认能力。"],
      ["做任务层改造", "优先改航点来源和动作触发层。", "不要直接从 /setpoints_cmd 或 px4ctrl 状态机下手。"],
      ["做扩展规划", "把 Elastic/FUEL/Formation/YOLO 放到独立路线图和后续验证任务里。", "不要和当前实机主链混写在一页速查表里。"],
    ],
    [220, 320, 320],
  );

  const rawSheet = workbook.worksheets.add("完整矩阵");
  const rawHeaders = [
    "feature_name",
    "wiki_or_pdf_mentioned",
    "repo_source_present",
    "onboard_deployed",
    "directly_runnable",
    "required_hardware",
    "primary_entrypoint",
    "verification_method",
    "include_in_main_quickref",
    "notes",
    "evidence_id",
  ];
  setColumnWidths(rawSheet, [160, 120, 120, 120, 120, 220, 220, 260, 150, 220, 120]);
  styleTitle(rawSheet, "完整矩阵", "这里保留完整原始字段。", rawHeaders.length);
  writeSection(
    rawSheet,
    4,
    "完整矩阵",
    rawHeaders,
    rows.map((row) => rawHeaders.map((header) => row[header] ?? "")),
    [160, 120, 120, 120, 120, 220, 220, 260, 150, 220, 120],
  );
  rawSheet.freezePanes.freezeRows(5);

  return workbook;
}

function createGapWorkbook(rows) {
  const workbook = Workbook.create();

  const guideSheet = workbook.worksheets.add("怎么用");
  setColumnWidths(guideSheet, [200, 220, 360]);
  styleTitle(
    guideSheet,
    "素材缺口表怎么用",
    "这一份不是开发接口表，而是给后续补截图、补培训材料的人用。P0 先补，P1 次之。",
    3,
  );
  writeSection(
    guideSheet,
    4,
    "阅读方式",
    ["你想做什么", "看哪里", "说明"],
    [
      ["确定先补哪些截图", "优先级列", "P0 是当前最影响日常使用的缺口。"],
      ["知道每张图为什么缺", "缺口明细", "这里把缺口原因和补采指令写清楚了。"],
      ["准备拍摄任务", "缺口明细", "直接按 collection_instruction 执行。"],
    ],
    [200, 220, 360],
  );

  const detailSheet = workbook.worksheets.add("缺口明细");
  setColumnWidths(detailSheet, [140, 220, 120, 200, 220, 260, 100]);
  styleTitle(detailSheet, "缺口明细", "这些缺口对应的是仍需补拍或补标注的日常使用素材。", 7);
  writeSection(
    detailSheet,
    4,
    "素材缺口",
    ["状态场景", "需要补什么", "当前情况", "证据来源", "为什么缺", "补采指令", "优先级"],
    rows.map((row) => [
      row.state_group,
      row.required_shot,
      row.currently_available,
      row.evidence_source,
      row.gap_reason,
      row.collection_instruction,
      row.priority,
    ]),
    [140, 220, 120, 200, 220, 260, 100],
  );
  detailSheet.freezePanes.freezeRows(5);

  return workbook;
}

async function saveWorkbook(workbook, outPath) {
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outPath);
}

await fs.mkdir(OUT_ROOT, { recursive: true });

await saveWorkbook(
  createInterfaceWorkbook(payload.interface_rows),
  path.join(OUT_ROOT, "非凸α-接口总表.xlsx"),
);
await saveWorkbook(
  createFeatureWorkbook(payload.feature_rows),
  path.join(OUT_ROOT, "非凸α-功能部署矩阵.xlsx"),
);
await saveWorkbook(
  createGapWorkbook(payload.gap_rows),
  path.join(OUT_ROOT, "非凸α-素材缺口表.xlsx"),
);

console.log("WROTE", path.join(OUT_ROOT, "非凸α-接口总表.xlsx"));
console.log("WROTE", path.join(OUT_ROOT, "非凸α-功能部署矩阵.xlsx"));
console.log("WROTE", path.join(OUT_ROOT, "非凸α-素材缺口表.xlsx"));
