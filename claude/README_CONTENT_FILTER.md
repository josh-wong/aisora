# Claude content-filtering system

This document describes the content-filtering system implemented for the Aisora's Claude integration to prevent inappropriate content from reaching the language model.

## Overview

The content-filtering system provides a multi-layered approach to filter and block inappropriate, illegal, or unethical requests before they reach Claude. It includes:

1. Pattern-based content detection
2. User restriction management
3. Comprehensive logging for audit and improvement
4. Integration with the existing request flow

## Components

### 1. Content filter (**content_filter.py**)

This is the core module that analyzes incoming messages and determines if they should be blocked. It uses:

- Regex pattern matching against inappropriate content categories
- User restriction status checking
- Context analysis to reduce false positives

### 2. Database integration

The system uses two main tables:

- **`user_restrictions`:** Tracks users with a history of inappropriate requests.
- **`filtered_requests`:** Logs all filtered requests for auditing and system improvement.

You can create these tables by running the **create_content_filter_tables.py** script.

### 3. User restriction management (**manage_user_restrictions.py**)

A command-line tool for managing user restrictions:

- Restrict users who repeatedly violate content policies.
- Remove restrictions when appropriate.
- List all currently restricted users.
- View detailed violation history for specific users.

## Usage

### Integrating the filter

The content filter is already integrated into the main flow in **aisora.py**. It automatically filters requests before they reach Claude.

### Managing user restrictions

```bash
# Restrict a user
python manage_user_restrictions.py restrict +1234567890 --reason "Multiple policy violations" --level "moderate"

# Remove a restriction
python manage_user_restrictions.py unrestrict +1234567890

# List all restricted users
python manage_user_restrictions.py list

# View violation history for a user
python manage_user_restrictions.py history +1234567890
```

### Creating database tables

To set up the required database tables:

```bash
python create_content_filter_tables.py
```

## How it works

1. When a user sends a message, the content is first passed to the `filter_content` function.
2. The function checks if the user is already restricted.
3. It then analyzes the content against predefined patterns of inappropriate content.
4. If the content is flagged, the request is blocked and the incident is logged.
5. The user receives a polite message explaining why their request cannot be processed.
6. After multiple violations, users can be restricted automatically or manually.

## Filtering categories

The system filters content in these categories:

- **Illegal activities:** Hacking, identity theft, counterfeit documents, etc.
- **Harmful content:** Instructions for weapons, violence, self-harm, etc.
- **Explicit content:** Sexually explicit content, especially involving minors
- **Unethical requests:** Academic dishonesty, spreading misinformation, etc.
- **Hate speech:** Racial slurs, inciting violence, etc.

## False-positive reduction

The system incorporates mechanisms to reduce false positives:

- Legitimate contexts (academic, creative writing, etc.) are considered.
- Pattern matching is designed to understand intent rather than just keywords.
- Appeal process available for wrongfully restricted users.

## Maintenance and improvement

The filtering system should be regularly updated:

- Review logs of filtered requests to identify patterns.
- Add new patterns for emerging inappropriate content.
- Refine existing patterns to reduce false positives.
- Update the legitimate contexts list as needed.

## Technical notes

- The filtering happens before any API calls to Claude, saving costs and protecting the system.
- User restrictions are stored in the database for persistence across restarts.
- All filtered requests are logged with timestamps for auditing and system improvement.
