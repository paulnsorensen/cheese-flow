# TypeScript / JavaScript De-slop Patterns

Language-specific patterns the `age-deslop` dim looks for in TypeScript/JavaScript diffs.
Read alongside `protocol.md` (cross-language patterns).

---

## 1. `any` as Escape Hatch

When types get complex, AI gives up and uses `any`, throwing away everything
TypeScript provides.

**What to look for:** Function parameters typed as `any`; return types of `any`;
`data: any` in API handlers or utility functions.

```typescript
// SLOP
function processData(data: any): any {
  return data.value;
}

// CLEAN
function processData<T extends { value: unknown }>(data: T): T['value'] {
  return data.value;
}

// Or if you genuinely don't know the shape:
function processData(data: unknown): unknown {
  if (hasValue(data)) return data.value;
  throw new Error("missing value field");
}
```

---

## 2. `.then()` Chains Instead of `async/await`

AI mixes paradigms or uses promise chains where async/await is cleaner.

**What to look for:** `.then().then().catch()` chains in new code where
`async/await` is available.

```typescript
// SLOP
function fetchUser(id: string) {
  return fetch(`/api/users/${id}`)
    .then(res => res.json())
    .then(data => data.user)
    .catch(err => console.error(err));
}

// CLEAN
async function fetchUser(id: string): Promise<User> {
  const res = await fetch(`/api/users/${id}`);
  return (await res.json()).user;
}
```

---

## 3. `console.log` Debugging Left In

AI adds debug logging that never gets removed.

**What to look for:** `console.log(...)`, `console.log("Fetching...", ...)`,
debug-flavored log strings in non-test code.

**Fix shape:** Delete all `console.log` debug statements. Use a proper logger
if observability is needed, or remove entirely if the code is self-evident.

---

## 4. `Array.forEach` With Async Callbacks

`forEach` doesn't await — async callbacks fire and are silently dropped.

**What to look for:** `items.forEach(async (item) => { await ... })`.

```typescript
// SLOP — these await calls do nothing useful
items.forEach(async (item) => {
  await processItem(item);
});

// CLEAN — sequential
for (const item of items) {
  await processItem(item);
}

// CLEAN — concurrent with control
await Promise.all(items.map(item => processItem(item)));
```

---

## 5. Redundant Null Checks TypeScript Already Handles

With `strictNullChecks`, the compiler enforces null safety.

**What to look for:** `=== null || === undefined` checks on values the type
system already guarantees are non-null; double-null-checks on typed fields.

```typescript
// SLOP — name can't be undefined here, the type says string | null
function greet(name: string | null): string {
  if (name === null || name === undefined) {
    return "Hello, stranger";
  }
  return `Hello, ${name}`;
}

// CLEAN
function greet(name: string | null): string {
  return name ? `Hello, ${name}` : "Hello, stranger";
}
```

---

## 6. `JSON.parse(JSON.stringify())` for Deep Cloning

**What to look for:** `JSON.parse(JSON.stringify(x))` used where `structuredClone`
is available (all modern runtimes).

```typescript
// SLOP
const cloned = JSON.parse(JSON.stringify(user));

// CLEAN
const cloned = structuredClone(user);
```

---

## 7. Redundant Type Annotations on Initialized Variables

**What to look for:** Type annotations on variables whose type is unambiguous
from the initializer (literals, constructor calls, typed function returns).

```typescript
// SLOP
const count: number = 0;
const name: string = user.name;
const isActive: boolean = true;
const users: User[] = getUsers();

// CLEAN — inference handles these
const count = 0;
const name = user.name;
const isActive = true;
const users = getUsers();

// Keep annotations on empty collections or ambiguous initializers
const users: User[] = [];
```

---

## 8. Over-Importing from Barrel Files

**What to look for:** Import statements that pull 4+ named exports from a
single module when only 1-2 are used.

```typescript
// SLOP — grabs everything, bloats bundle
import { UserService, UserModel, UserDTO, UserMapper, UserValidator } from "./users";

// CLEAN — import only what you use
import { UserService } from "./users";
```
