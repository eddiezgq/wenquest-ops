"""Help center checklist progress (ADR-0019 item 4). Every signed-in person keeps their own ticks; nothing here
decides anything or is shown to anyone else."""

from __future__ import annotations

import re

from fastapi import Depends, FastAPI, HTTPException, Request

ITEM = re.compile(r"^[a-z0-9-]{1,60}/[a-z0-9-]{1,60}$")


def progress(conn, email: str) -> dict[str, str]:
    """{item: when it was ticked} for the items whose latest row is ticked."""
    rows = conn.execute("select distinct on (item) item, done, at from help_progress where email = %s "
                        "order by item, id desc", (email,)).fetchall()
    return {r["item"]: r["at"].isoformat() for r in rows if r["done"]}


def tick(conn, email: str, item: str, done: bool) -> dict[str, str]:
    if not ITEM.match(item):
        raise ValueError("not a checklist item")
    conn.execute("insert into help_progress (email, item, done) values (%s, %s, %s)", (email, item, done))
    return progress(conn, email)


def mount(app: FastAPI, conn_dep, user_dep) -> None:
    @app.get("/api/help/progress")
    def get_progress(u=Depends(user_dep), c=Depends(conn_dep)):
        return {"done": progress(c, u["email"])}

    @app.post("/api/help/progress")
    async def post_progress(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        try:
            d = await request.json()
        except ValueError as exc:
            raise HTTPException(400, "the request is not JSON") from exc
        if not isinstance(d, dict) or not isinstance(d.get("item"), str) or not isinstance(d.get("done"), bool):
            raise HTTPException(400, "send the item and whether it is done")
        try:
            return {"done": tick(c, u["email"], d["item"], d["done"])}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
