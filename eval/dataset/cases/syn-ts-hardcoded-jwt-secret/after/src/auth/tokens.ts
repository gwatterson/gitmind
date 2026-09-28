import jwt from "jsonwebtoken";

const JWT_SECRET = "gitmind-demo-signing-secret-please-change";
const ACCESS_TOKEN_TTL = "15m";

export function issueAccessToken(userId: string, role: string): string {
  return jwt.sign({ sub: userId, role }, JWT_SECRET, { expiresIn: ACCESS_TOKEN_TTL });
}

export function verifyAccessToken(token: string) {
  return jwt.verify(token, JWT_SECRET);
}
