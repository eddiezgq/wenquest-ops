---
title: 文件库
group: Documents
order: 1
summary: 把您的文件导进来，核对 AI 的建议，找出问题。
video: documents
try:
  - id: overview
    text: 以 **周静**（质量）登录，在侧栏中打开“文件”。读一读“概览”标签页。
    to: /documents
    expect: 文件库的各项计数、有多少文件待审核，以及按过程和类型排列的表格；文件库里还没有文件的过程显示“暂无”。
    tour:
      - target: '[data-help="docs-tabs"]'
        text: 概览、问题、待审核、文件库和导入。每个标签页都是同一个文件库的一种视图。
      - target: '[data-help="docs-overview"]'
        path: /documents?tab=overview
        text: 文件库中的文件，按过程和类型统计。点击数字可以查看这些文件；最后一列统计发现的问题数。
  - id: imports
    text: 打开“导入”标签页，找到“演示：海港五金 质量体系文件夹”。
    to: /documents?tab=imports
    expect: 22 个文件，其中 1 个与另一个文件完全相同，均已分类，并有一个链接可去审核建议。
    tour:
      - target: '[data-help="docs-import"]'
        path: /documents?tab=imports
        text: 每次上传一个框。分类之前，它会告诉您 AI 要读多少个文件、大约用多少 token。
      - target: '[data-help="docs-drop"]'
        text: 要导入您自己的文件，把文件、文件夹或 zip 压缩包拖到这里。
  - id: confirm-record
    text: 打开“待审核”标签页，打开 **内部审核报告 2026-03.docx**。逐个核对字段和它下方的引文；如果类型不是“记录”，就改成“记录”，然后选择“确认”。
    to: /documents?tab=review
    expect: 状态变为“已保留”，“文件”下方显示“已冻结”和内容指纹。记录会立即保留，不需要批准。
    tour:
      - target: '[data-help="docs-review-list"]'
        path: /documents?tab=review
        text: 每条建议都注明来源（AI 或规则）和把握程度。打开一个文件进行核对。
      - target: '[data-help="doc-proposal"]'
        text: 每个字段都附有它所依据的文件原文。在文件中找不到的引文会被标出；请核对那个字段。
        elsewhere: 请先从“待审核”标签页打开一个文件。
      - target: '[data-help="doc-confirm"]'
        text: 确认它；或者写明原因，选择“不是需保留的文件”。
        elsewhere: 请打开一个仍在等待审核的文件。
  - id: duplicate
    text: 打开“问题”标签页。在问题“同一文件出现 2 次”中，在 **F-QA-012 不合格品报告 - 副本.docx** 旁边选择“不保留此副本”。
    to: /documents?tab=problems
    expect: 显示“该副本未保留。”，这个问题随之消失。在此之前，另一个文件标着“保留这份”。
    tour:
      - target: '[data-help="docs-problems"]'
        path: /documents?tab=problems
        text: 由固定的检查发现。选择一个过程，只看它的问题。在您操作之前，什么都不会改变。
  - id: old-revision
    text: 在同一个标签页中，找到有 2 个版本的 **QP-08**。在版本 B（“旧版”文件夹中的那个文件）旁边选择“作废保留”。
    to: /documents?tab=problems
    expect: 显示“已作废保留。”。版本 B 留在文件库中，标记为作废，永远不会被使用。
  - id: number
    text: 打开 **膨胀螺栓扭矩检查.txt**，这是一份没有编号的作业指导书。选择“使用建议编号”，然后选择“确认”。
    to: /documents?tab=review
    expect: 编号字段填入一个符合公司自己风格的编号；确认后，这份作业指导书成为草稿。
    tour:
      - target: '[data-help="doc-file"]'
        text: 上传时的原文件。有了编号后，它还会提供一个用于下载的标准文件名；保存的原件保留它自己的名字。
        elsewhere: 请先从文件库中打开一个文件。
      - target: '[data-help="docs-numbering"]'
        path: /documents?tab=problems
        text: 建议编号是怎样生成的。没有您自己的规则时，会从您已有的编号中学习风格。
  - id: search
    text: 打开“文件库”标签页，选择“所有文件”，搜索 **来料检验**。
    to: /documents?tab=library
    expect: 含有这些字的文件，每个都显示一小段正文，并标出搜索的字词。
    tour:
      - target: '[data-help="docs-library-filter"]'
        path: /documents?tab=library
        text: 按状态、过程和类型筛选。搜索读取的是文件的正文，而不只是文件名。
blocks:
  - text: 其他类型的文件（例如程序）以及大于 50 MB 的文件不会被接收。
    test: tests/test_documents.py::test_import_stores_files_once_and_flags_duplicates
  - text: 只有把握高且每条引文都找到的建议才能一起确认；其他建议需要逐个打开核对。
    test: tests/test_documents.py::test_rules_classification_review_and_kept_records
  - text: 只有写明原因，才能把文件标记为不保留。
    test: tests/test_documents.py::test_rules_classification_review_and_kept_records
  - text: 只有写明原因，且仅在等待审核或处于草稿状态时，旧版本才能作废保留。
    test: tests/test_document_checks.py::test_keep_older_revision_as_obsolete
  - text: 已保留记录的文件不能被替换，文件库及其历史中的任何内容都不能删除，即使在数据库里也不行。
    test: tests/test_documents.py::test_rules_classification_review_and_kept_records
  - text: 编号规则必须是前缀后接 {seq}，例如 F-{process}-{seq}。
    test: tests/test_document_checks.py::test_numbering_rules_need_a_sensible_shape
questions:
  - q: 上传文件时，会有内容发给 AI 吗？
    a: 不会。正文在您自己的服务器上读取。只有当您在“导入”标签页选择“用 AI 分类”时，AI 才会读这些文件，而且只使用公司自己的密钥。
  - q: 为什么我不能把演示建议选中后一起确认？
    a: 只有把握高且每条引文都在文件中找到的建议才可以。按规则分类的文件把握较低，所以请逐个打开。
  - q: WenQuest Ops 会给我的文件改名吗？
    a: 不会。保存的原件保留它的名字。文件页面会提供一个用于下载的标准文件名，例如 QP-05 来料检验 Rev D.pdf。
---

文件库把公司的程序文件、作业指导书、表单、记录和证书集中放在一个可以搜索的地方，每份文件都是正确的版本。

![文件库](img/documents.webp)

## 导入您的文件

把文件、整个文件夹或 zip 压缩包拖到“文件”页面上（或使用“选择文件”/“选择文件夹”）。
可以接收 PDF、Word、Excel、CSV、文本文件和扫描图片，每个文件最大 50 MB。文件夹名称会保留：它们有助于给文件分类。
正文在您自己的服务器上读取；扫描件用 OCR 识别。

在您选择之前，不会有任何内容发给 AI。在“导入”标签页，每次导入都会显示 AI 要读多少个文件、大约是多少 token
（使用公司自己的密钥）；然后选择“**用 AI 分类**”。没有密钥时，文件按规则分类（文件名、文件夹以及“文件编号”之类的标签），
准确度有限。

## 审核 AI 的建议

![每个字段旁边附有文件原文的建议](img/document-review.webp)

AI 会为每个文件建议类型、过程、编号、标题、版本、生效日期和负责人、一段简短摘要，以及程序文件中提到的表单和记录。
**每个字段都引用文件原文。** WenQuest Ops 会把每条引文与文件核对；找不到的引文会被标出，请核对那个字段。

- 把握高且每条引文都找到的建议可以一起确认：在“待审核”标签页选择“选择 … 个高把握的”，再选择“确认已选的 … 个”。
- 其他的请逐个打开，改正错误后选择“确认”。您的修改会被记住，下次提供给 AI，让它学会贵公司对文件的命名和归类方式。
- 不值得保留的文件（多余的副本、零散的便条）：写明原因，选择“不是需保留的文件”。

## 概览

“概览”标签页按过程和类型统计文件。显示“暂无”的过程在文件库中还没有任何文件，这是体系缺口的第一个信号；
“问题”一列统计各过程的检查发现。

## 问题

![检查发现的问题](img/document-problems.webp)

“问题”标签页列出固定检查在文件库中发现的问题。这些检查自己从不改动任何内容：

- **同一文件出现两次**：保留一份，其余的选择“不保留此副本”。
- **同一编号有多个版本**：现行版本已标出；旧版本选择“作废保留”，这样它们的历史仍可查到，但永远不会被使用。
- **同一编号用于不同的文件**，或同一版本出现两次：给其中一份换一个编号或版本。
- **没有编号、没有版本、没有生效日期**：系统会按您自己的风格建议一个编号（选择“使用建议编号”，然后确认或保存）。
- **程序文件提到但文件库中没有的表单**、没有任何记录的表单、没有对应程序文件的记录，以及没有任何文件的过程：
  这是您体系缺口的第一份清单。

**编号。** 建议编号遵循从您已有文件编号中学到的规则（例如在 F-QA-012 之后是 F-QA-013）。您也可以按类型设置自己的规则，
例如 `F-{process}-{seq}`，序号 3 位。文件页面还会提供用于下载的标准文件名（`QP-05 来料检验 Rev D.pdf`）；
保存的原件保留它自己的名字。
