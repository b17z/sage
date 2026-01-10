# Engineering Principles

Core philosophy for building reliable, maintainable software.

## Code Philosophy

### Functional by Default
- Pure functions over stateful objects
- Immutability by default
- Composition over inheritance
- "Could this just be a function?" — usually yes

### Errors as Values
- Return Result types instead of throwing exceptions
- Force callers to handle both success and failure
- Reserve exceptions for truly exceptional conditions

### Layered Architecture
- Dependency flows downward only
- Domain logic free from framework coupling
- Clear boundaries between layers

## Code Design

### Simplicity
- Minimize complexity for the current task
- Avoid premature abstraction
- Three similar lines > premature helper function
- Don't design for hypothetical future requirements

### Clarity
- Code as documentation
- Explicit over implicit
- Boring, proven solutions over clever architecture

### Security
- Validate at system boundaries
- Trust internal code and framework guarantees
- Don't add unnecessary defensive code

## Error Handling

```python
@dataclass(frozen=True)
class Ok[T]:
    value: T

@dataclass(frozen=True)
class Err[E]:
    error: E

type Result[T, E] = Ok[T] | Err[E]
```

Pattern match on results:
```python
match get_user(id):
    case Ok(user):
        return process(user)
    case Err(error):
        return handle_error(error)
```
