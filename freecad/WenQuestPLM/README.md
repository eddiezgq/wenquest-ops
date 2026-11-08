# 问渠 PLM · FreeCAD 插件（WenQuest PLM add-on）

把 FreeCAD 模型（零件、装配结构、每个零件的 STEP）推送到问渠质量 ERP 的“设计数据”收件箱，由工程师核对后签字写入（ADR-0026，26e）。

安装：把 `WenQuestPLM` 文件夹复制到 FreeCAD 的 Mod 目录（工具 → 宏 → 用户宏位置的上一级 `Mod`），重启 FreeCAD。

1. 老板在质量 ERP“集成”页新建一把钥匙，勾“plm:send”。
2. FreeCAD 里切到 “WenQuest PLM” 工作台（缝纫机工作台也有这两个按钮），点“问渠 PLM 设置”，填质量 ERP 地址和钥匙。
3. 打开模型，点“推送到 PLM”。

认什么：App::Part、装配（Assembly）是部件；PartDesign 实体（Body）和不在实体里的 Part 形体是零件；链接（Link）指向它链接的对象，
同一个零件装几次就算几个。零件属性里有 PartNumber / Code / WQCode 就作为编码带上；设了材料（ShapeMaterial）就带材料和按密度算的质量。
