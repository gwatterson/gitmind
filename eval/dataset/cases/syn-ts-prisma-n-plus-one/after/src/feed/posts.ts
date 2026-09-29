import { prisma } from "../db";

export async function latestPosts(limit = 20) {
  return prisma.post.findMany({ orderBy: { createdAt: "desc" }, take: limit });
}

export async function feed(limit = 20) {
  const posts = await latestPosts(limit);
  const items = [];
  for (const post of posts) {
    const author = await prisma.user.findUnique({ where: { id: post.authorId } });
    items.push({ id: post.id, title: post.title, author: author?.name ?? "unknown" });
  }
  return items;
}
