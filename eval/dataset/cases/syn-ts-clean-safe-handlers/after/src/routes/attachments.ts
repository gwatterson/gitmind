import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import { Router } from "express";
import jwt from "jsonwebtoken";
import { pool } from "../db";

const run = promisify(execFile);
const ATTACHMENTS = path.resolve(process.env.ATTACHMENTS_DIR ?? "/srv/attachments");

export const attachmentsRouter = Router();

attachmentsRouter.use((req, res, next) => {
  const token = req.headers.authorization?.replace(/^Bearer /, "") ?? "";
  try {
    res.locals.user = jwt.verify(token, process.env.JWT_SECRET as string);
    next();
  } catch {
    res.sendStatus(401);
  }
});

attachmentsRouter.get("/attachments/:name", async (req, res) => {
  const target = path.resolve(ATTACHMENTS, req.params.name);
  if (!target.startsWith(ATTACHMENTS + path.sep)) {
    return res.sendStatus(400);
  }
  const { stdout } = await run("file", ["--brief", "--mime-type", target]);
  res.type(stdout.trim()).sendFile(target);
});

attachmentsRouter.get("/attachments", async (req, res) => {
  const { rows } = await pool.query(
    "SELECT name, size FROM attachments WHERE owner_id = $1 AND name ILIKE $2 LIMIT 50",
    [res.locals.user.sub, `%${String(req.query.q ?? "")}%`],
  );
  res.json(rows);
});
