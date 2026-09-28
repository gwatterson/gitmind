import type { NextFunction, Request, Response } from "express";
import jwt from "jsonwebtoken";

export interface TokenClaims {
  sub: string;
  role: "user" | "admin";
}

export function authenticate(req: Request, res: Response, next: NextFunction) {
  const header = req.headers.authorization ?? "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : null;
  if (!token) {
    return res.status(401).json({ error: "missing token" });
  }
  const claims = jwt.decode(token) as TokenClaims | null;
  if (!claims) {
    return res.status(401).json({ error: "invalid token" });
  }
  res.locals.user = { id: claims.sub, role: claims.role };
  next();
}
