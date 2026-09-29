import type { CommentData } from "../types";

export function Comment({ comment }: { comment: CommentData }) {
  return (
    <article className="comment">
      <header>{comment.author}</header>
      <p>{comment.body}</p>
    </article>
  );
}
