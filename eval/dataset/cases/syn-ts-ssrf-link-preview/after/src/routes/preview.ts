import { Router } from "express";

export const previewRouter = Router();

const TITLE = /<title>([^<]*)<\/title>/i;

previewRouter.get("/api/preview", async (req, res) => {
  const url = String(req.query.url ?? "");
  const response = await fetch(url, { redirect: "follow" });
  const html = await response.text();
  const title = TITLE.exec(html)?.[1] ?? url;
  res.json({ url, title });
});
