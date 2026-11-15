"""WenQuest PLM add-on: three commands (settings, push, exploded view), also offered to other workbenches (the sewing
machine workbench adds them)."""
import FreeCAD as App
import FreeCADGui as Gui


class _Settings:
    def GetResources(self):
        return {"MenuText": "问渠 PLM 设置 / WenQuest PLM settings",
                "ToolTip": "质量 ERP 地址和钥匙 / address of the quality ERP and the access token"}

    def Activated(self):
        import wqplm_net as N
        from PySide import QtGui
        s = N.settings()
        server, ok = QtGui.QInputDialog.getText(None, "WenQuest PLM", "质量 ERP 地址 / address (https://...)",
                                                text=s["server"])
        if not ok:
            return
        token, ok = QtGui.QInputDialog.getText(None, "WenQuest PLM", "钥匙 / access token (wqo_...)",
                                               text=s["token"])
        if not ok:
            return
        N.save_settings(server, token)
        try:
            who = N.whoami()
            ok_send = "plm:send" in who.get("scopes", [])
            QtGui.QMessageBox.information(None, "WenQuest PLM", f"已连上 / connected: {who.get('name')}" +
                                          ("" if ok_send else "\n这把钥匙没有 plm:send / this token lacks plm:send"))
        except Exception as e:
            QtGui.QMessageBox.warning(None, "WenQuest PLM", str(e))


class _Push:
    def GetResources(self):
        return {"MenuText": "推送到 PLM / Push to PLM",
                "ToolTip": "零件、装配结构和每个零件的 STEP 送进质量 ERP 的设计数据收件箱，由工程师核对写入"}

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        import wqplm_doc as D
        from PySide import QtGui
        try:
            r = D.push(App.ActiveDocument)
            more = ""
            if r.get("outside"):
                more = ("\n链接到其他文件的没有送，请在那个文件里推送 / links to other files were not sent: " +
                        "、".join(r["outside"][:10]))
            QtGui.QMessageBox.information(
                None, "WenQuest PLM", f"已送出 / sent: #{r.get('id')}，{r.get('parts')} 个零件 / parts。"
                "\n到质量 ERP“工程设计 → 设计数据”核对写入 / review it in Design data." + more)
        except Exception as e:
            QtGui.QMessageBox.warning(None, "WenQuest PLM", str(e))


class _Explode:
    def GetResources(self):
        return {"MenuText": "生成爆炸图 / Exploded view",
                "ToolTip": "选一个装配：自动拉开、放序号、出线条图，送到 PLM 等人确认 / select an assembly: pull it "
                           "apart, number the parts, draw it and send it to the PLM to be confirmed"}

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        import wqplm_doc as D
        import wqplm_explode as X
        from PySide import QtGui
        sel = [o for o in Gui.Selection.getSelection() if o.TypeId in D.ASSEMBLY]
        if len(sel) != 1:
            QtGui.QMessageBox.information(None, "WenQuest PLM",
                                          "请先选一个装配（App::Part）/ select one assembly first")
            return
        try:
            r = X.make(sel[0])
            more = ""
            if r.get("without_3d"):
                more += "\n没有三维的行 / lines without 3D: " + "、".join(r["without_3d"][:12])
            if r.get("not_on_bom"):
                more += "\n不在 BOM 上的 / not on the BOM: " + "、".join(r["not_on_bom"][:12])
            QtGui.QMessageBox.information(
                None, "WenQuest PLM", f"已送出 / sent: BOM {r.get('revision')}，{r.get('balloons')} 个序号 / balloons。"
                "\n到 PLM 爆炸图页确认 / confirm it on the exploded view page." + more)
        except Exception as e:
            QtGui.QMessageBox.warning(None, "WenQuest PLM", str(e))


Gui.addCommand("WQPLM_Settings", _Settings())
Gui.addCommand("WQPLM_Explode", _Explode())
Gui.addCommand("WQPLM_Push", _Push())


class WenQuestPLMWorkbench(Gui.Workbench):
    MenuText = "WenQuest PLM"
    ToolTip = "问渠 PLM：把模型推送到质量 ERP / push the model to the WenQuest quality ERP"

    def Initialize(self):
        self.appendToolbar("WenQuest PLM", ["WQPLM_Push", "WQPLM_Explode", "WQPLM_Settings"])
        self.appendMenu("WenQuest PLM", ["WQPLM_Push", "WQPLM_Explode", "WQPLM_Settings"])

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(WenQuestPLMWorkbench())
