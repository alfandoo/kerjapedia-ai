# Frontend dependency rules

The frontend follows a one-way dependency direction:

```text
app -> features -> shared
```

- `app/` composes routes from feature public entrypoints.
- Each feature owns its components, API functions, and domain types.
- Routes and other features import a feature through its `index.ts` public entrypoint when practical.
- Files inside a feature use direct internal imports to keep bundles explicit and avoid barrel cycles.
- Shared code in `components/ui`, `components/icons.tsx`, `hooks/`, and `lib/` must not import feature modules.
- Cross-feature imports must target the owning feature; types must not be duplicated.
