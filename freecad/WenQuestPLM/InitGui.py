"""WenQuest PLM add-on: two commands, also offered to other workbenches (the sewing machine workbench adds them)."""
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
            QtGui.QMessageBox.information(
                None, "WenQuest PLM", f"已送出 / sent: #{r.get('id')}，{r.get('parts')} 个零件 / parts。"
                "\n到质量 ERP“工程设计 → 设计数据”核对写入 / review it in Design data.")
        except Exception as e:
            QtGui.QMessageBox.warning(None, "WenQuest PLM", str(e))


Gui.addCommand("WQPLM_Settings", _Settings())
Gui.addCommand("WQPLM_Push", _Push())


class WenQuestPLMWorkbench(Gui.Workbench):
    MenuText = "WenQuest PLM"
    ToolTip = "问渠 PLM：把模型推送到质量 ERP / push the model to the WenQuest quality ERP"

    def Initialize(self):
        self.appendToolbar("WenQuest PLM", ["WQPLM_Push", "WQPLM_Settings"])
        self.appendMenu("WenQuest PLM", ["WQPLM_Push", "WQPLM_Settings"])

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(WenQuestPLMWorkbench())
