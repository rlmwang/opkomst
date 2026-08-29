/**
 * Run a composable outside a component.
 *
 * A composable that subscribes to something does it in an effect, and
 * an effect needs an owner. A component is one; ``$effect.root`` is the
 * other, and it is the one a test wants: no markup, and a teardown it
 * calls itself.
 */
export async function inEffect<T>(body: () => T | Promise<T>): Promise<T> {
  let result!: T | Promise<T>;
  const dispose = $effect.root(() => {
    result = body();
  });
  try {
    return await result;
  } finally {
    dispose();
  }
}
