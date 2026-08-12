# Studio Voxel — Business Website & CMS

Studio Voxel is a database-driven architecture studio website with a protected admin workspace. Public pages read services, projects, gallery items and business information from the FastAPI + MongoDB API; authenticated editors can update that content without editing source code.

## Stack

- React 19, React Router, Axios, Tailwind utilities, Lucide icons
- FastAPI, Motor, Pydantic, PyJWT, bcrypt, python-multipart
- MongoDB (existing `MONGO_URL` and `DB_NAME` configuration)
- Local image storage in `backend/uploads/`

## Run locally

1. Confirm `backend/.env` contains `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, `JWT_SECRET`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD`.
2. Install backend dependencies: `pip install -r backend/requirements.txt`.
3. Install frontend dependencies: `cd frontend && yarn install`.
4. The workspace supervisor runs FastAPI on `0.0.0.0:8001` and React on its configured port. For a manual frontend session use `yarn start` from `frontend`.

The seeded admin credentials are stored in `/app/memory/test_credentials.md`. Open `/admin/login` to enter the workspace.

## Content workflow

Use the admin sidebar to manage Services, Projects, Gallery, Media and Business Settings. Uploads are validated as JPG, PNG or WEBP under 8 MB, saved with a unique filename in `backend/uploads/`, and represented in MongoDB by metadata. Public content refreshes when the public route loads.

## API overview

`POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`, `GET /api/site/home`, `GET/PUT /api/settings`, `GET/PUT /api/content/{page}`, CRUD `/api/services`, CRUD `/api/projects`, `/api/projects/{slug}`, CRUD `/api/gallery`, `GET/POST/DELETE /api/media`, `GET /api/dashboard`, and `POST /api/contact`.

## Production notes

Keep secrets in environment variables, do not commit `backend/uploads/*`, use HTTPS for admin sessions, and configure `CORS_ORIGINS` to the exact public frontend origin rather than `*` when cookie authentication is required.