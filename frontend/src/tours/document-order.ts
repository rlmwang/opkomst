/** Negative when ``a`` comes before ``b`` in the document, positive
 *  after, zero for the same node. A comparator over the DOM's own
 *  ``compareDocumentPosition`` bit field. */
export function compareDocumentPosition(a: Node, b: Node): number {
  if (a === b) return 0;
  const pos = a.compareDocumentPosition(b);
  if (pos & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
  if (pos & Node.DOCUMENT_POSITION_PRECEDING) return 1;
  return 0;
}
