/**
 * An ordered list of sub-editors, with add, move and delete.
 *
 * The question editor and the chore editor are the same list: an array
 * of rows a page reorders by index. This owns the array and the
 * mutations, so a page supplies only the item factory and the row
 * component.
 *
 * Display order is array order. There is no ordinal field here; a
 * caller that needs a 1..N derives it from the index at submit time,
 * which keeps this purely positional.
 *
 * Date poll slots are deliberately not built on this: they are a
 * date-keyed map with common slots and exclusions, and no order.
 */
export function orderedList<T>(initial: T[] = []) {
  let items = $state<T[]>(initial);

  return {
    get items(): T[] {
      return items;
    },
    /** Replace the whole list, for loading a row or restoring a draft. */
    set items(next: T[]) {
      items = next;
    },
    add(item: T): void {
      items.push(item);
    },
    removeAt(index: number): void {
      items.splice(index, 1);
    },
    replaceAt(index: number, next: T): void {
      items[index] = next;
    },
    /** Swap with the neighbour ``delta`` away. Out of bounds does
     *  nothing. */
    move(index: number, delta: -1 | 1): void {
      const target = index + delta;
      if (target < 0 || target >= items.length) return;
      [items[index], items[target]] = [items[target], items[index]];
    },
  };
}
