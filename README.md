# Preferences

This repository is a directory of files which label and specify all of the preferences that I have for all kinds of things in life. It is used to direct AI agents for how exactly they should complete tasks on my behalf.

The purpose is to give AI agents all kinds of context on all kinds of different things so that they know how to handle tasks for me.

## How to use this repository

**Start with [`profile.md`](./profile.md)** — it gives a quick holistic picture of who I am before you dive into any specific category.

Each top-level folder represents a category of preferences. Within each folder, markdown files describe specific preferences, requirements, and constraints for that category. AI agents should consult the relevant files before making decisions or completing tasks that fall under a given category. Every folder contains an `index.md` with a summary of the category and a listing of its files.

When there's no explicit preference file for a decision, **ask me** — don't guess.

## Directory

| Folder | Description |
|--------|-------------|
| [beverages](./beverages/) | Preferences related to drinks and hydration. Covers daily go-to drinks, coffee orders, and beverage habits. |
| [communication](./communication/) | Preferences related to how I communicate and prefer to be communicated with. Covers tone, preferred channels, response time expectations, and formality levels. |
| [daily-routine](./daily-routine/) | Preferences related to daily structure and habits. Covers morning routines, evening wind-down, and general rhythm of the day. |
| [education](./education/) | Preferences related to learning and personal development. Covers learning style, subject interests, course platforms, and self-improvement goals. |
| [emergency](./emergency/) | Information and preferences related to emergency preparedness, insurance, and handling unexpected situations — especially relevant as a digital nomad living abroad. |
| [entertainment](./entertainment/) | Preferences related to leisure and media consumption. Covers movies, television, books, video games, streaming services, and hobbies. |
| [fashion](./fashion/) | Preferences related to clothing and personal style. Covers preferred brands, sizing, shopping habits, dress code comfort levels, and wardrobe philosophy. |
| [finance](./finance/) | Preferences related to money management and spending. Covers budgeting philosophy, investing approach, spending habits, and financial goals. |
| [fitness](./fitness/) | Preferences related to exercise and physical activity. Covers workout routines, gym vs. home training, preferred activities, equipment, and fitness goals. |
| [food](./food/) | Preferences related to food, cooking, and dining. Covers dietary restrictions, cuisine preferences, favorite restaurants, meal planning habits, and grocery shopping. |
| [gifts](./gifts/) | Preferences related to giving and receiving gifts. Covers budget ranges, preferred gift types, occasions, and wishlists. |
| [health](./health/) | Preferences related to healthcare and wellness. Covers medical provider preferences, supplement and medication habits, mental health practices, and wellness routines. |
| [home-decor](./home-decor/) | Preferences related to interior design and furnishing. Covers aesthetic style, color palettes, furniture brands, and spatial organization philosophy. |
| [housing](./housing/) | Preferences related to residential properties. Covers minimum requirements for size, layout, amenities, and other factors considered when evaluating a place to live. Splits time between the US (mid-April to Nov 1) and Mexico (Nov 1 to mid-April). |
| [languages](./languages/) | Preferences related to spoken and written languages. Covers fluency levels, languages being actively studied, and communication language preferences. |
| [music](./music/) | Preferences related to music and audio. Covers preferred genres, artists, listening habits, and streaming services. |
| [personal-brand](./personal-brand/) | Preferences related to online presence, social media, and professional reputation. Covers which platforms I use, how I post, and goals for building a presence in the tech / AI space. |
| [pets](./pets/) | Preferences related to animals and pet ownership. Covers preferred animals, care standards, veterinary expectations, and pet-related purchasing. |
| [productivity](./productivity/) | Preferences related to time management, planning, and personal organization. Covers how I structure my time outside of work, handle unwanted tasks, and protect free time. |
| [relationships](./relationships/) | Preferences related to how I build and maintain relationships — family, partner, friendships, and professional connections. |
| [shopping](./shopping/) | Preferences related to shopping habits and purchasing behavior. Covers online vs. in-store preferences, secondhand shopping, and general approach to buying things. |
| [social](./social/) | Preferences related to social life and gatherings. Covers event types, hosting style, group size preferences, and social cadence. |
| [sustainability](./sustainability/) | Preferences related to environmental consciousness and ethical purchasing. Covers how sustainability factors into buying decisions, lifestyle choices, and brand preferences. |
| [technology](./technology/) | Preferences related to devices, software, and digital services. Covers operating systems, hardware brands, development tools, apps, subscriptions, and smart home setup. |
| [travel](./travel/) | Preferences related to travel and vacations. Covers destination preferences, accommodation standards, airline and seating choices, packing habits, and trip planning style. |
| [values](./values/) | Core personal values and guiding principles. These inform decision-making across all other preference categories. |
| [vehicles](./vehicles/) | Preferences related to cars and transportation. Covers vehicle type, brand preferences, features, fuel type, and commute preferences. |
| [work](./work/) | Preferences related to productivity and work environment. Covers scheduling, tooling, workspace setup, meeting preferences, and workflow habits. |

## Improvement Roadmap

Recommendations for making this repository more useful to AI agents, roughly ordered by impact.

### 1. Deepen High-Frequency Categories

The housing and food sections are the most developed, but categories agents would reference most often — work, communication, daily-routine, technology, and values — are among the thinnest. Prioritize fleshing these out since they inform the widest range of tasks.

### 2. Reframe Content as Decision Rules

The best files in this repo (like `housing/deal-breakers.md` and `housing/inspection-checklist.md`) give agents clear decision criteria: reject if X, require Y, prefer Z. Many other files read more as descriptions than instructions. Reframe content around what an agent should *do* with the information — thresholds, priorities, and constraints — not just what is true.

### 3. Add Frontmatter Metadata

Preferences change over time. Adding a simple YAML frontmatter block to each file with `last_reviewed:` (and optionally `confidence: high | medium | low`) helps agents gauge how much to trust older content.

```yaml
---
last_reviewed: 2026-02-28
confidence: high
---
```

### 4. Add a Top-Level Profile Summary

Create a `profile.md` that gives agents a quick holistic picture — key facts, personality traits, overarching priorities — before they dive into any specific category. This prevents agents from missing cross-cutting context.

### 5. Clean Up Vision Boards

The `vision_boards/2026/` structure has monthly and seasonal subdirectories, but most are empty or just headers. Either populate them with real goals and intentions, or simplify to quarterly/seasonal boards. Empty structure can mislead agents into thinking there is content to reference.

### 6. Add Cross-References Between Categories

Categories are currently siloed, but preferences interact: sustainability values affect shopping, dietary preferences affect the grocery list, work schedule affects daily routine. Add links between related files so agents can follow the thread. For example, `shopping/habits.md` should reference `sustainability/philosophy.md`.

### 7. Add Missing High-Value Categories

Some significant life areas are not yet represented:

- **Relationships / people** — friendship maintenance, family contact cadence, networking style
- **Productivity / time management** — prioritization system, focus strategies, planning methodology
- **Personal brand / online presence** — social media philosophy, professional bio preferences
- **Emergency / contingency** — what to do if X happens, important contacts, insurance preferences

### 8. Add Lightweight Tooling

The repo is pure markdown with no automation. Consider adding:

- A script or GitHub Action that flags files not updated in 6+ months
- A template for new category creation so structure stays consistent
- A generated table of contents in this README that stays in sync with the actual directory tree
