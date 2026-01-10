# Senior Engineer Review Checklist

Multi-persona review questions for comprehensive analysis.

## Security Engineer

- What are the attack vectors?
- How could this be exploited?
- What data is exposed and to whom?
- Are inputs validated at boundaries?
- Are secrets properly managed?

## Performance Engineer

- What are the scaling bottlenecks?
- Where are the N+1 queries?
- What's the memory profile?
- How does this behave under load?
- Are there caching opportunities?

## Product Manager

- Does this solve the user's actual problem?
- What's the simplest version that works?
- What edge cases will users encounter?
- How will users discover this feature?
- What metrics indicate success?

## Data Engineer

- How does data flow through the system?
- What's the data retention policy?
- How is PII handled?
- What analytics are needed?
- How does this affect data pipelines?

## DevOps Engineer

- How is this deployed?
- What monitoring is needed?
- How do we roll back?
- What are the dependencies?
- How does this affect CI/CD?

## QA Engineer

- What are the test cases?
- What's the edge case coverage?
- How do we test failure modes?
- What's the regression risk?
- How do we verify in production?

## Using This Checklist

When reviewing designs or implementations:

1. Pick 2-3 relevant personas
2. Ask their questions
3. Document gaps and concerns
4. Prioritize by risk and effort
5. Address critical issues first
