# siakam_callgraph_creator 设计文档

## 概述

开发一个由 markdown 文档和 Python 脚本组成的 SKILL，名为 `siakam_callgraph_creator`。核心功能：生成 C 语言项目（内核驱动、固件代码）的 call graph，要求高准确率。

目标代码类型：手机系统底层驱动代码，包括 Linux 内核驱动、鸿蒙内核驱动、手机非主核（GPU, sensorhub, ISP 等）固件驱动、启动链代码（UEFI, fastboot, xloader 等）。不含用户态 C 代码。

---

## 使用方法

```
/siakam_callgraph_creator project_dir
```

- `project_dir`：待分析项目路径，默认当前文件夹
- 若 `project_dir` 中存在 `.siakamignore` 文件，排除匹配的文件/目录（语法同 `.gitignore`）

---

## 整体架构

采用方案 1：单一 Python 工具 + SKILL 编排，三模块架构。

```
/siakam_callgraph_creator project_dir
    │
    ├── Python 脚本: 模块A → 解析C代码，输出 nodes.json + edges.json + indirect_points.json
    │
    ├── SKILL (LLM): 模块B → 读取 indirect_points.json，并行分析每个间接调用
    │       每个结果写入 .siakam_out/indirect/<uid>.json
    │       断点续跑：已有 <uid>.json 的跳过
    │
    └── Python 脚本: 模块C → 合并 A+B 结果，生成最终输出
```

---

## SKILL 目录结构

```
siakam_callgraph_creator/
├── skill.md                    # SKILL入口
├── module_a/
│   ├── analyzer.py             # 入口：协调解析流程
│   ├── ignore_parser.py        # 解析 .siakamignore
│   ├── c_parser.py             # tree-sitter 解析C代码
│   ├── indirect_detector.py    # 检测函数指针调用点
│   ├── uid_generator.py        # 为间接调用点生成uid
│   ├── models.py               # 数据模型
│   └── tests/
│       ├── test_ignore_parser.py
│       ├── test_function_detection.py
│       ├── test_direct_edges.py
│       ├── test_indirect_detection.py
│       ├── test_syntax_error.py
│       ├── test_macro_handling.py
│       └── fixtures/           # 测试用C代码
├── module_b/
│   ├── analyze_indirect.md     # 单间接调用分析提示词模板
│   └── orchestrator.md         # 主编排提示词
└── module_c/
    ├── merge.py                # 合并结果生成callgraph
    └── entry_finder.py         # 查找入度为0的函数
```

---

## 输出目录结构

运行时在被分析项目的 `project_dir` 下生成：

```
<project_dir>/.siakam_out/
├── nodes.json              # 模块A输出：所有函数节点
├── edges.json              # 模块A输出：所有直接调用边
├── indirect_points.json    # 模块A输出：所有间接调用点（含uid）
├── indirect/               # 模块B输出
│   ├── <uid1>.json
│   ├── <uid2>.json
│   └── ...
├── callgraph.json          # 模块C输出：完整调用图
├── callgraph.dot           # 模块C输出：Graphviz格式
├── indirect_call.json      # 模块C输出：间接调用汇总
└── entry.json              # 模块C输出：入度为0函数列表
```

---

## 模块 A 详细设计

### 功能

1. 解析 `.siakamignore`，确定分析范围
2. 识别项目中全部函数（call graph 中的点）
3. 识别全部直接函数调用（call graph 中的边）
4. 识别每个有函数体的函数中的间接调用点（函数指针），不需分析具体目标

### 数据模型

**nodes.json — 函数节点：**

```json
{
  "project_dir": "/path/to/project",
  "functions": [
    {
      "name": "my_driver_probe",
      "file": "drivers/foo/bar.c",
      "line_start": 42,
      "has_body": true,
      "body_file": "drivers/foo/bar.c",
      "body_line_start": 42,
      "body_line_end": 98
    },
    {
      "name": "some_external_func",
      "file": "include/foo/api.h",
      "line_start": 15,
      "has_body": false,
      "body_file": null,
      "body_line_start": null,
      "body_line_end": null
    }
  ]
}
```

字段说明：
- `file` — 声明所在文件路径（相对 project_dir）；有函数体的写函数体位置，无体的写声明位置，无声明则 null
- `has_body` — true 表示有函数体实现
- `body_file` — 函数体位置（有体时同 file，跨文件实现时不同），无体为 null
- `body_line_start` / `body_line_end` — 函数体行号范围

**edges.json — 直接调用边：**

```json
{
  "edges": [
    {
      "caller": "my_driver_probe",
      "callee": "kmalloc",
      "file": "drivers/foo/bar.c",
      "line": 56
    }
  ]
}
```

**indirect_points.json — 间接调用点：**

```json
{
  "indirect_points": [
    {
      "uid": "a3f2b1c4",
      "func": "my_driver_probe",
      "file": "drivers/foo/bar.c",
      "line": 60,
      "expression": "ops->read"
    }
  ]
}
```

uid 计算：`sha256("file:func:line:expression")[:8]`

### 实现方案

| 文件 | 职责 |
|------|------|
| `ignore_parser.py` | 解析 `.siakamignore`，仿 gitignore 语法，返回 exclude 路径模式列表 |
| `c_parser.py` | 使用 tree-sitter-c 解析单文件，提取函数节点、直接调用边、间接调用点 |
| `indirect_detector.py` | AST 遍历辅助：判断 call_expression 是否通过函数指针调用 |
| `uid_generator.py` | `hash(file:func:line:expression)` 返回 sha256 前 8 位 hex |
| `models.py` | dataclass 定义 FunctionNode, DirectEdge, IndirectPoint |

### 解析策略

- 使用 tree-sitter C grammar，不依赖编译
- 对语法错误：打印警告（文件:行号），跳过错误所在函数，继续解析其余部分
- 宏处理：尽最大努力识别源码中宏体里的函数调用；对无法解析的宏用法标记 warning
- 准确率目标：在代码语法正确的前提下，100% 准确率（0 漏报 0 误报）

### 测试

配套功能测试，使用 fixture C 代码片段验证解析正确性。

---

## 模块 B 详细设计

### 功能

深入分析模块 A 找到的间接调用，明确 caller-callee 对应关系。由 LLM 完成，纯 markdown 提示词，禁止使用任何脚本和代码。

### 分析范围

caller 必须在项目文件夹内有函数体实现。caller 实现不在项目内的边不关注。

### 编排流程

1. 读取 `indirect_points.json`
2. 检查每个 uid 对应的 `indirect/<uid>.json`：
   - 存在且 `status == "completed"` → 跳过
   - 存在且 `status == "failed"` → 跳过或可选重试
   - 不存在 → 加入待分析列表
3. 将待分析列表拆分为 batch（每个 batch ≤ 5 个间接调用）
4. 为每个 batch 启动一个 subagent 并行分析
5. 每个 subagent 独立完成分析，写入 `indirect/<uid>.json`

### 单个分析结果格式

```json
{
  "uid": "a3f2b1c4",
  "status": "completed",
  "possible_targets": [
    {
      "callee": "my_read",
      "file": "drivers/foo/bar.c",
      "confidence": "high",
      "reasoning": "直接赋值 ops->read = my_read 在同一文件中"
    }
  ]
}
```

- `status`：
  - `completed` — 分析完成（possible_targets 可为空，表示充分分析后无法确定任何目标）
  - `failed` — 分析过程出错（如无法读取源文件、LLM 调用异常等），需记录 error 字段
- `confidence` — `high` | `medium` | `low`

### 分析提示词关键要素

1. 输入上下文：uid, func, file, line, expression
2. 分析步骤：
   - 读取所在文件和关联头文件
   - 定位函数指针的类型声明
   - 追踪指针在 caller 函数上下文中的赋值来源
   - 跨文件追踪（结构体初始化赋值、结构体传递路径等）
   - 列出所有可能的 callee 目标，标注 confidence
3. 利用 LLM 对 Linux/鸿蒙内核框架的知识补全分析
4. 能力边界：充分分析后仍无法确定目标，输出空 target 列表并记录原因

### 防护措施

- 主编排使用 checklist 逐项追踪每个 uid，避免任务遗忘
- 每个 subagent 处理不重叠的 batch，共享无状态，避免相互影响
- 分析完成立即写入文件，不攒批，保证断点续跑可靠性

---

## 模块 C 详细设计

### 功能

综合模块 A 和 B 的结果，生成最终输出。

### 流程

1. 读取 nodes.json, edges.json, indirect_points.json
2. 遍历 indirect_points.json，读取每个 indirect/<uid>.json
3. 将 possible_targets 转换为 callgraph 边
4. 输出四个文件

### 输出文件

**callgraph.json：**

```json
{
  "nodes": [...],
  "edges": [
    {"caller": "my_driver_probe", "callee": "kmalloc", "type": "direct", "file": "drivers/foo/bar.c", "line": 56},
    {"caller": "my_driver_probe", "callee": "my_read", "type": "indirect", "uid": "a3f2b1c4", "confidence": "high"}
  ]
}
```

**callgraph.dot：** Graphviz 格式，节点为函数名，边标注类型和 confidence。

**indirect_call.json：** 模块 B 分析结果的汇总视图，包含 total/completed/failed 统计和每个调用的详情。

**entry.json：** 所有 has_body=true 且入度为 0（不被任何其他函数调用）的函数列表。

### 各文件职责

| 文件 | 职责 |
|------|------|
| `merge.py` | 读取 A+B 结果，合并为 callgraph.json 和 callgraph.dot |
| `entry_finder.py` | 基于 callgraph 计算入度为 0 的函数，输出 entry.json 和 indirect_call.json |

---

## 测试方案

测试集参考基准：`/home/admin/cc/wksp/siakam_security_skills/test_bench`，包含 12 个分类、104 个 C 语言间接调用场景 fixture。生成测试用例时需预分析校验各 ground_truth 的准确性。

### 模块 A 测试

**目标：** 验证 Python tree-sitter 解析器能正确识别函数节点、直接调用边、间接调用点。

**fixture 组织：** 从 test_bench 复制 fixture.c，新增模块 A 专属 ground truth：

```
module_a/tests/fixtures/<category>/<example>/
├── fixture.c                  # 从 test_bench 复制
├── ground_truth_nodes.json    # 期望的函数节点
├── ground_truth_edges.json    # 期望的直接调用边
└── ground_truth_indirect.json # 期望的间接调用点
```

**测试用例：**

| 测试文件 | 测试内容 | 覆盖范围 |
|---------|---------|---------|
| `test_ignore_parser.py` | `.siakamignore` 解析（glob 匹配、目录排除、否定模式） | 4-5 个 ignore 场景 |
| `test_function_detection.py` | 函数节点识别：有体函数、声明、static、跨文件 | 各分类选取代表性 fixture |
| `test_direct_edges.py` | 直接调用识别：普通调用、宏内调用、嵌套调用链 | 跨分类选取含直接调用的 fixture |
| `test_indirect_detection.py` | 间接调用点识别：12 种模式全覆盖，验证 uid 计算 | 全部 104 个 fixture |
| `test_syntax_error.py` | 语法错误处理：跳过错误函数、继续解析其余、警告输出 | 手工构造 3-4 个错误 fixture |
| `test_macro_handling.py` | 宏定义内调用识别 | 构造含宏的 fixture |

### 模块 B 测试

模块 B 是 LLM 驱动，测试核心是验证提示词质量。

**B1. 提示词功能测试（手动/半自动）：**

```
module_b/tests/
├── fixtures/                  # indirect_point JSON 格式（每分类 2-3 个，约 30 个）
├── expected/                  # 精标注的期望分析结果
└── run_analysis_test.md       # 测试流程提示词
```

验证项：
- `possible_targets` 是否覆盖全部 expected callee
- `confidence` 是否合理
- 是否存在误报（报告了不存在的 target）

**B2. 编排提示词测试：**

验证断点续跑、任务不遗漏、并行 subagent 隔离：

```
module_b/tests/
├── mock_indirect_points.json  # 模拟模块A输出（含 6 个 uid）
├── pre_existing/              # 预置结果文件（uid1 completed, uid3 failed）
└── run_orchestrator_test.md   # 编排测试流程
```

### 模块 C 测试

**目标：** 验证合并逻辑和入度计算的正确性。

```
module_c/tests/
├── fixtures/
│   ├── nodes.json
│   ├── edges.json
│   ├── indirect_points.json
│   └── indirect/              # 模拟模块B输出（completed/failed/空targets）
└── expected/
    ├── callgraph_expected.json
    ├── callgraph_expected.dot
    ├── indirect_call_expected.json
    └── entry_expected.json
```

**测试用例：**

| 测试文件 | 测试内容 |
|---------|---------|
| `test_merge.py` | 合并直接+间接边；边类型标注（direct/indirect）；failed 状态处理；callgraph.dot 格式 |
| `test_entry_finder.py` | 入度为 0 的 has_body 函数；环形调用无 entry；外部无体函数调用不影响入度；空图处理 |
| `test_indirect_summary.py` | total/completed/failed 统计；空 targets 显示；汇总与目录文件一致性 |

### 端到端集成测试

```
tests/
├── e2e_project/               # 小型完整项目，含多种间接调用模式
│   ├── .siakamignore
│   ├── driver.c / ops.c
│   └── include/api.h
├── expected/                  # 全部输出文件的期望值
│   ├── nodes.json, edges.json, indirect_points.json
│   ├── indirect/<uid>.json
│   ├── callgraph.json, callgraph.dot
│   ├── indirect_call.json, entry.json
└── run_e2e_test.md
```

**验证项：**
1. `/siakam_callgraph_creator e2e_project/` 完整执行
2. `.siakam_out/` 所有输出与 expected/ 对比
3. 断点续跑：删除部分 `indirect/<uid>.json`，验证只重新分析缺失项
4. `.siakamignore` 排除验证：被忽略文件中的函数不出现在节点中

---

## 全局约束

1. **异常中断兼容**：每一步结果都存入文件；每个间接调用以 uid 命名结果文件；任务中断重启后已有结果的跳过
2. **模块 B 审批**：模块 B 的提示词需声明工具使用权限（Bash/Read/Glob/Write），SKILL 提前申请
3. **不依赖编译**：分析基于源码静态解析，不要求代码可编译
4. **caller 范围**：边只包含 caller 在项目内有实现的调用，外部 caller 忽略
5. **模块 B 锁文件**：分析前创建 `indirect/<uid>.json` 并写入 `status: "in_progress"`，避免并发冲突

---

## 数据流图

```
.siakamignore ──→ ignore_parser ──→ exclude_paths
                                         │
project_dir/*.c,*.h ────────────────────→ c_parser ──→ nodes.json
                                                    ├─→ edges.json
                                                    └─→ indirect_points.json
                                                              │
                              ┌────────────────────────────────┘
                              ▼
                   indirect_points.json
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
         subagent1       subagent2       subagentN
             │                │                │
             ▼                ▼                ▼
        <uid1>.json      <uid2>.json     <uidN>.json
             │                │                │
             └────────────────┼────────────────┘
                              ▼
                     merge.py + entry_finder.py
                              │
                    ┌─────────┼──────────┐
                    ▼         ▼          ▼
            callgraph.json  callgraph.dot
                    │         │
                    ▼         ▼
            indirect_call.json
                    │
                    ▼
              entry.json
```
