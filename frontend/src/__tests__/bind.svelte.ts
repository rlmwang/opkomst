/**
 * A bindable prop a test can read back.
 *
 * ``bind:value`` on a call site is the parent handing the child a way
 * to write the value back. A test renders the child with no parent, so
 * it passes an accessor instead: the child's write lands in the setter,
 * and the test reads what it wrote.
 *
 * The accessor has to be defined on the object that is handed over.
 * Spreading it into another object would copy the current value and
 * lose the setter, which is why the rest of the props go through here
 * too.
 *
 * The value behind it is reactive state, not a plain variable. A
 * component reads its own bindable prop back, and a multi-select
 * toggling a row off is exactly that: without a signal to re-read, the
 * write reaches the test and the component still sees the old value.
 */
export function bindable<T, P = Record<string, unknown>>(
  name: string,
  initial: T,
  rest: Record<string, unknown> = {},
) {
  let current = $state(initial);
  const writes: T[] = [];
  const props: Record<string, unknown> = { ...rest };
  Object.defineProperty(props, name, {
    enumerable: true,
    configurable: true,
    get: () => current,
    set: (next: T) => {
      current = next;
      writes.push(next);
    },
  });
  return {
    // The accessor is defined by name at runtime, so it is not on the
    // literal's type. The caller says what the component asks for.
    props: props as P,
    get current() {
      return current;
    },
    /** Every value the component wrote, oldest first. */
    get writes() {
      return writes;
    },
    get last() {
      return writes.at(-1);
    },
  };
}
