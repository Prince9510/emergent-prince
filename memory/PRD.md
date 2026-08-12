# Studio Voxel Product Requirements

## Original problem statement
Build a production-quality professional business website plus secure admin CMS, FastAPI backend, MongoDB database, local image upload/management, dynamic content, authentication, validation, responsive UI, SEO foundations, documentation and living project memory.

## Architecture decisions
- Keep the provided React + FastAPI + MongoDB environment rather than replacing it with Node.
- Use application UUIDs and Pydantic response shapes to avoid MongoDB ObjectId serialization issues.
- Store image bytes locally and metadata in MongoDB.
- Use JWT/bcrypt for one seeded admin and protect all write APIs.
- Use an original Swiss/editorial architecture-studio design system named Studio Voxel.

## Personas
- Studio owner/editor: logs into the CMS, updates projects, services, gallery, media and business details.
- Prospective client: browses work, understands the studio offer and sends an enquiry.

## Core requirements (static)
Public home, about, services, projects and detail, gallery/lightbox, contact; protected admin login/dashboard; CRUD for services/projects/gallery; media uploads and deletion; settings; responsive accessible interface; validation and friendly states.

## Implemented — 2026-03-10
- Premium responsive public site with seeded database-driven content.
- Protected admin workspace with dashboard statistics, CRUD modals, media library and settings editor.
- JWT login with bcrypt, bearer token support, secure cookie, content validation and local upload validation.
- MongoDB indexes, seed admin/content, static upload serving, contact storage, SEO metadata and unique data-testid selectors.
- QA fixes: bearer JWTs are revoked on logout and Media Library renders explicit loading, error and empty states.

## Implemented — 2026-08-12
- Testimonials section on the homepage with a rotating 3-card carousel, dot navigation and 5-star rating.
- Journal (blog) with public listing and slug-based detail pages, and full admin CRUD (auto-slug from title).
- Team members on the About page with photo, role, bio and social links; admin CRUD.
- FAQ page with grouped accordions per category; admin CRUD.
- AdminCrud generalised to support textarea and checkbox field types.
- Dashboard extended to 8 resource stat cards.

## Prioritized backlog
- P1: Filter public `/api/blog` list to only return published+active posts (frontend currently filters).
- P1: Handle blog slug collisions with a friendly 409 instead of a 500 on duplicate title.
- P1: Add admin page-content editor and media picker for content records.
- P2: Add admin inbox for stored contact submissions.
- P2: Add multiple admins/roles, image resizing and richer project image galleries.