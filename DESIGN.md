# DESIGN.md

## High-level architecture

The application is architected as a dynamic Python Flask web application that serves HTML content using Jinja2 templates. Persistent storage is managed through two distinct SQLite databases: users.db handles user sessions and authentication data, while problems.db stores the educational content such as problems, topics, and user attempts. Static assets, including CSS, images, fonts, and figures, are served directly from the /static directory. A core component of the architecture is a custom server-side pipeline that leverages Pandoc to convert LaTeX problem text and answers into renderable HTML.

## Routes and responsibilities

The application's routing logic manages user flow across authentication, study, and recreation. The root route (/) acts as a dashboard or landing page depending on the user's session state, while /register, /login, and /logout handle secure authentication, automatically logging users in upon registration. For account management, /account_settings allows users to update credentials. The core educational experience is driven by /study, which selects problems and dynamically converts their LaTeX content to HTML, and /progress, which visualizes study statistics and reviews incorrect attempts. Finally, the /break route (and its associated sub-routes like /blotchville) serves as a gateway to the Stat110-themed minigames.

## Templates and static assets

The frontend is built using Jinja2 templates stored in the templates/ directory, extending a master layout.html that integrates Bootstrap and site branding. Styling is defined in static/styles.css, complemented by a specialized computer-modern.css file that imports LaTeX-like fonts to maintain the aesthetic of the original course materials. Figures referenced within the problem text are stored in static/figures/, with the server dynamically rewriting their source attributes to ensure they render correctly on the web.

## LaTeX rendering pipeline

To display complex mathematical content, the application implements a multi-stage rendering pipeline. First, raw LaTeX snippets from the database are sanitized by _clean_latex_text(), which strips comments and rewrites incompatible macros (e.g., converting \displaylimits to \limits) or image references to prefer PNG formats. Next, _latex_to_html() invokes Pandoc (via pypandoc or a subprocess) with MathML support to convert the cleaned text into HTML. Finally, _rewrite_image_paths() post-processes the output to ensure image src attributes point to the correct static directory.

Rationale: The LaTeX source code that stores the problems is meant to render inside a LaTeX document, but it does not render well inside an HTML website. Therefore, the workaround was to convert the LaTeX to HTML first with the third-party pandoc package, and then render that HTML directly. Along the way, fixes were implemented to render the images and custom commands that had been defined in the LaTeX document.

## Database schema

We used two SQLite3 databases, users.db and problems.db. The first stores information about user logins and the video games users play; the second stores information relating to the practice problems. This separation allows the set of problems to be updated or replaced without risking data loss for user accounts or game history. 

The problems.db database serves as the repository for static educational content and study tracking. It centers on the problems table, which stores the core LaTeX text, answers, and metadata for each practice question. A topics table and a many-to-many problem_topics join table allow individual problems to be tagged with multiple concepts. Additionally, this database houses the problem_attempts table, which logs user activity by recording which problems a user has attempted, the result (correct or incorrect), and the timestamp, enabling the "Study Progress" features.

The users.db database manages authentication and the interactive study game statistics. Beyond the standard users table for credentials, it includes specialized tables for each game: leaderboard tracks high scores for Blotchville; monty_stats logs every decision (switch vs. stay) to calculate live probability statistics for the user; and the cafe_votes table utilizes a composite primary key of user_id and category to enforce a "one vote per category" rule, ensuring that the community poll reflects only the most recent preference of each user.

## Import script and data flow

The data import process is handled by a specialized script that reads CSV rows and populates the problems.db database with problems and their related topics. This architecture was explicitly designed for scalability, allowing the site administrators to easily update the source CSV with new content and re-insert it into the pipeline without manual database entry. Additionally, the script handles data migration for problem_attempts, mapping legacy columns to the current schema and attempting to associate each attempt with a canonical problems.id. To ensure data integrity, any attempts that fail this mapping are logged and skipped, or assigned to a fallback topic such as "Any" to prevent crashes during import.

## Interactivity

While Flask handles the routing and database management on the server, significant logic resides in the browser to create an interactive experience. "Blotchville" is rendered entirely on an HTML5 <canvas>, utilizing a JavaScript game loop powered by requestAnimationFrame to handle collision detection, entity spawning, and score tracking at 60 frames per second. The Monty Hall simulation relies on vanilla JavaScript DOM manipulation to orchestrate animations—such as door opening and closing—and to dynamically update CSS for prize reveals. Crucially, these games communicate with the backend via asynchronous fetch() calls to endpoints like /submit_score and /monty_save, allowing user statistics to be saved to the SQLite user.db database in the background without reloading the page or interrupting gameplay.

## Styling decisions

Building on the official Stat110 logo, styling is stored in static/styles.css. Everything relating to the practice problems is themed in blue and includes the logo in static/stat110-logo.png. The games mostly follow their own color themes, although the same shades of blue and the logo still feature. 

## Security & operational notes

To ensure the security of user accounts, the application strictly adheres to best practices for credential management. Passwords are never stored in plain text within the database; instead, the system utilizes the werkzeug.security library to hash passwords before saving them. By employing functions such as generate_password_hash and check_password_hash, the application ensures that sensitive user credentials remain protected even in the event of unauthorized database access.

## Known limitations and future work

The current architecture has a few known limitations that could be addressed in future iterations. First, the application relies on a system-level dependency, Pandoc, to convert LaTeX content into HTML. While this preserves the flexibility to add new problems dynamically at runtime, a production-ready version might pre-compile these snippets to remove the dependency on the end-user's environment. Additionally, the image handling pipeline relies on heuristics that assume a corresponding PNG exists for every figure referenced in the LaTeX source. While this was manageable for the current small dataset, a more robust asset pipeline would be required to automatically extract and convert figures for a larger library of problems.
