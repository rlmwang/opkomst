/**
 * Ordered-list editor state.
 *
 * The "an ordered array of sub-editors with add / move-up / move-down /
 * delete" shape used by the form-question editor (and the chore editor,
 * task 04). Owns the array and the index-based mutations so a parent
 * page only supplies the item factory + the per-row editor component.
 *
 * Display order IS array order; there is no ``ordinal`` field here —
 * callers that need a 1..N ordinal derive it from the index at submit
 * time (as ``FormEditPage`` does), keeping this list purely positional.
 *
 * (Datepoll slots are deliberately NOT built on this — they're a
 * date-keyed map with common-slots/exclusions and no ordering.)
 */

import { type Ref, ref } from "vue";

export function useOrderedList<T>(initial: T[] = []) {
  const items = ref(initial) as Ref<T[]>;

  /** Replace the whole list (used when loading/restoring a draft). */
  function set(next: T[]): void {
    items.value = next;
  }

  function add(item: T): void {
    items.value.push(item);
  }

  function removeAt(index: number): void {
    items.value.splice(index, 1);
  }

  function replaceAt(index: number, next: T): void {
    items.value[index] = next;
  }

  /** Swap the item at ``index`` with its neighbour ``delta`` away.
   * No-op if the target is out of bounds. */
  function move(index: number, delta: -1 | 1): void {
    const target = index + delta;
    if (target < 0 || target >= items.value.length) return;
    const arr = items.value;
    [arr[index], arr[target]] = [arr[target], arr[index]];
  }

  const moveUp = (index: number): void => move(index, -1);
  const moveDown = (index: number): void => move(index, 1);
  const canMoveUp = (index: number): boolean => index > 0;
  const canMoveDown = (index: number): boolean => index < items.value.length - 1;

  return { items, set, add, removeAt, replaceAt, move, moveUp, moveDown, canMoveUp, canMoveDown };
}
