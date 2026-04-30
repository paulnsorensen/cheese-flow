# Go De-slop Patterns

Language-specific patterns the `age-deslop` dim looks for in Go diffs.
Read alongside `protocol.md` (cross-language patterns).

---

## 1. Error String Conventions

Go errors are lowercase, no trailing punctuation, and wrap with `%w`.

**What to look for:** Capitalized error strings; trailing periods; use of `%v`
(breaks error chain) where `%w` is appropriate.

```go
// SLOP
return fmt.Errorf("Failed to open file: %s", err)
return errors.New("User not found.")

// CLEAN
return fmt.Errorf("open file: %w", err)
return errors.New("user not found")
```

The `%w` verb wraps the error so callers can use `errors.Is`/`errors.As`.
Use `%v` only when you intentionally want to break the error chain.

---

## 2. Named Returns With Bare `return`

AI loves named returns. They obscure which values are being returned.

**What to look for:** Functions with named return variables that use bare
`return` statements in non-`defer` contexts.

```go
// SLOP
func getUser(id int) (user *User, err error) {
    user = db.Find(id)
    if user == nil {
        err = errors.New("not found")
        return
    }
    return
}

// CLEAN
func getUser(id int) (*User, error) {
    user := db.Find(id)
    if user == nil {
        return nil, errors.New("user not found")
    }
    return user, nil
}
```

Named returns are acceptable only in `defer` recovery patterns.

---

## 3. `context.TODO()` Permanently

AI scaffolds with `context.TODO()` and never replaces it.

**What to look for:** `context.TODO()` in request handlers or service methods
that already have an incoming context available.

```go
// SLOP
func handleRequest(w http.ResponseWriter, r *http.Request) {
    ctx := context.TODO()
    result, err := db.Query(ctx, query)
}

// CLEAN — use the context you already have
func handleRequest(w http.ResponseWriter, r *http.Request) {
    result, err := db.Query(r.Context(), query)
}
```

`context.TODO()` means "I haven't decided which context to use yet."
In production code, you should always have decided.

---

## 4. Pointer to Interface

Almost never correct. Interfaces are already reference types.

**What to look for:** Parameters typed as `*SomeInterface` where `SomeInterface`
is an interface (not a concrete struct).

```go
// SLOP
func NewService(repo *Repository) *Service { ... }
// where Repository is an interface

// CLEAN
func NewService(repo Repository) *Service { ... }
```

---

## 5. Goroutine Leaks

AI spawns goroutines without cancellation paths.

**What to look for:** Goroutines with infinite loops and no `ctx.Done()` select
case; goroutines spawned without any way to signal them to stop.

```go
// SLOP — runs forever, no way to stop it
go func() {
    for {
        doWork()
        time.Sleep(time.Second)
    }
}()

// CLEAN — respects context cancellation
go func(ctx context.Context) {
    ticker := time.NewTicker(time.Second)
    defer ticker.Stop()
    for {
        select {
        case <-ctx.Done():
            return
        case <-ticker.C:
            doWork()
        }
    }
}(ctx)
```

---

## 6. `fmt.Sprintf` for String Concatenation in Loops

O(n²) string building.

**What to look for:** `fmt.Sprintf("%s%s", result, s)` inside a loop;
repeated `result +=` string concatenation.

```go
// SLOP
var result string
for _, s := range items {
    result = fmt.Sprintf("%s%s", result, s)
}

// CLEAN
var b strings.Builder
for _, s := range items {
    b.WriteString(s)
}
result := b.String()
```

---

## 7. Stuttering Package Names

**What to look for:** Type names that repeat the package name:
`user.UserService`, `user.UserModel`.

```go
// SLOP — user.UserService, user.UserModel
package user
type UserService struct{}
type UserModel struct{}

// CLEAN — user.Service, user.Model
package user
type Service struct{}
type Model struct{}
```

---

## 8. `init()` for Non-Trivial Setup

AI puts complex initialization in `init()` which can't return errors
and runs at import time with no control.

**What to look for:** Database connections, network clients, or file I/O
inside `init()` functions; `log.Fatal` inside `init()`.

```go
// SLOP
func init() {
    db, err := sql.Open("postgres", os.Getenv("DATABASE_URL"))
    if err != nil {
        log.Fatal(err)  // Kills the process at import time
    }
    globalDB = db
}

// CLEAN — explicit initialization the caller controls
func NewDB(dsn string) (*sql.DB, error) {
    return sql.Open("postgres", dsn)
}
```
