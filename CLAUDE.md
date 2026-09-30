## Summary 

This is a project that provides several applications for managing iTunes library.
Applications will be implemented using Python and PyQt. WinCom API will be used for communication with iTunes.

Applications will include:
- iTunes playlist manual sorter
- iTunes metadata verifier
- iTunes new song importer
- iTunes to Spotify sync (bidirectional)

Project should be structured to house multiple applications with a common module that could be reused across different applications.

## Goals

This is a personal, single-developer, learning project. As such, the goal is to learn tools and technologies used.
AI coding will be used to a minimum, with AI taking an advisory role providing code snippets and debug support.

## Project Structure

UV environment location is not standard. Always set `UV_PROJECT_ENVIRONMENT=D:\venv\itunes-tools` before running any
scripts.

## Code Quality and Other Preferences

1. Use python zen – longer and simple is better than complex and short; explicit is better than implicit.
2. Use PEP8 style guide for code formatting, PyCharm style.
3. Use meaningful variable names, comments, and docstrings to improve code readability, but don't spam them.
    1. Docstrings should be in Restructured Text format.
4. DRY – look for existing code that could be easily reused.
5. Pydantic will be used for data validation – freeform dictionaries will be kept to a minimum.
5. When writing new code, stick to organizations and conventions established in the existing codebase.
6. Git - user is in control.
    1. Don't create branches or pull requests or make commits unless explicitly asked by the user.
    2. Branching model: `main` is always releasable; no direct commits to it. All work happens on short-lived branches off `main` – `feature/<issue#>-<short-name>` for use cases and enhancements, `bugfix/<issue#>-<short-name>` for bug fixes (a GitHub issue captures the requirements for each).
    3. Every branch is merged into `main` through a pull request, which is used for code review.
    4. Code should be covered by unit tests and formatted before committing.