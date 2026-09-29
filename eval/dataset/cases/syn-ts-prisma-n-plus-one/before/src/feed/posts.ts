import { prisma } from "../db";

export async function latestPosts(limit = 20) {
  return prisma.post.findMany({ orderBy: { createdAt: "desc" }, take: limit });
}
