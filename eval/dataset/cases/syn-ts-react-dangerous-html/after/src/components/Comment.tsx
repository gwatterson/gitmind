import type { CommentData } from "../types";

export function Comment({ comment }: { comment: CommentData }) {
  return (
    <article className="comment">
      <header>{comment.author}</header>
      <div className="comment-body" dangerouslySetInnerHTML={{ __html: comment.body }} />
    </article>
  );
}
