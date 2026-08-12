# Project Brain

## Project Overview
Studio Voxel is a premium architecture and interiors business website with a database-backed CMS. It uses a Swiss/editorial visual language: warm paper, charcoal ink, brass accents, Space Grotesk display type and generous asymmetric grids.

## Architecture
- React frontend in `/app/frontend`, React Router routes public and admin experiences.
- FastAPI backend in `/app/backend/server.py`, MongoDB via Motor, REST API under `/api`.
- Public content is seeded once for a complete first visit and then managed through admin CRUD.
- Images are stored in `/app/backend/uploads` and served only through `/uploads/{filename}`.

## Database Models
`users`, `settings`, `page_content`, `services`, `projects`, `gallery`, `media`, `contact_submissions`, `testimonials`, `blog`, `team`, `faqs`, and `revoked_tokens`. Documents have application UUIDs and ISO timestamps; API queries exclude Mongo `_id`. `projects` and `blog` have unique indexes on `slug`.

## Authentication
JWT + bcrypt. Admin is seeded from `ADMIN_EMAIL` and `ADMIN_PASSWORD`. Frontend stores the access token for bearer requests and the backend also sets a secure httpOnly cookie. Protected routes use `current_admin`.

## API Routes
Auth: `/api/auth/login`, `/api/auth/me`, `/api/auth/logout`.
Site: `/api/site/home` (now returns testimonials + team alongside services/projects/gallery), `/api/settings`, `/api/content/{page}`, `/api/contact`.
Content: CRUD `/api/services`, CRUD `/api/projects`, `/api/projects/{slug}`, CRUD `/api/gallery`.
Extended content: CRUD `/api/testimonials`, CRUD `/api/team`, CRUD `/api/faqs`, CRUD `/api/blog`, `/api/blog/{slug}`.
Media/admin: `/api/media`, `/api/media/upload`, `/api/dashboard` (stats now cover 8 collections).

## Current Status
Completed: public Home (with rotating testimonials band), About (with team grid), Services, Projects/detail, Gallery lightbox, Blog listing + detail, FAQ accordion, Contact; admin login, dashboard (8 stat cards), services/projects/gallery/testimonials/team/blog/faqs CRUD with unified AdminCrud (textarea + checkbox support), media upload/delete, business settings; responsive styling, SEO title/meta, loading/empty/error states, data-testid coverage, seed content and documentation. Logout revokes bearer JWTs through the `revoked_tokens` collection.

## Change History
- 2026-03-10: Replaced starter screen with Studio Voxel public site and admin CMS.
- 2026-03-10: Added JWT admin authentication, MongoDB seed content, CRUD APIs, local media upload, and responsive editorial design.
- 2026-03-10: Fixed logout token revocation and hardened the media library empty/error flow after QA.
- 2026-08-12: Added Testimonials (homepage carousel), Blog/Journal (listing + slug detail), Team (About page grid), and FAQs (grouped accordion) with full admin CRUD; AdminCrud now supports textarea and checkbox field types; dashboard stats extended to 8 resource counts.

## Known Limitations
- Gallery records reference image URLs; a media asset picker can be added later to connect uploaded media directly to content forms.
- Contact submissions are stored but not yet surfaced in an admin inbox or emailed.
- Page-content editing UI is not exposed yet; homepage/about seed records are API-ready for a future editor screen.

## Development Commands
Frontend: `cd frontend && yarn install && yarn start`, `yarn build`.
Backend dependencies: `pip install -r backend/requirements.txt`.
Supervisor manages the backend on port 8001; do not run a second uvicorn server.

## Environment Variables
Backend uses existing `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS` plus `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`. Frontend uses protected `REACT_APP_BACKEND_URL`.
