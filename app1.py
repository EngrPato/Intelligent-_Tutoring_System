import os
from math import pi
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from owlready2 import World, get_ontology

# ---------------------------
# Configuration
# ---------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


ONTO_FILE = os.path.join(BASE_DIR, "area_ontology.owl") 
ONTO_URI = "file://" + ONTO_FILE # Keep for reference

app = Flask(__name__)

app.secret_key = "a-secure-random-key" 

# ---------------------------
# Ontology Setup and Core Access Helpers
# -----------------------------------------------------

world = World()
onto = None
try:
    # Attempt to load the ontology
    onto = world.get_ontology(ONTO_FILE).load(format = "rdfxml") 
    print(f"Ontology loaded successfully from: {ONTO_FILE}")
except Exception as e:
    # Catch loading errors and stop the app
    raise RuntimeError(f"FATAL ERROR: Failed to load ontology file at {ONTO_FILE}. Check file path and format (should be RDF/XML/OWL): {e}")

# Class Access Helper 
def get_onto_class(class_name):
    """Safely retrieves a class from the ontology object."""
    cls = getattr(onto, class_name, None)
    if cls is None:
        flash(f"Ontology Class '{class_name}' not found. Check if the class exists and the ontology is loaded.", "danger")
        return None
    return cls

# Save helper
def save_ontology():
    """Safely saves the ontology to the file."""
    try:
        onto.save(file=ONTO_FILE, format="rdfxml") 
    except Exception as e:
        flash(f"ERROR: Failed to save ontology file: {e}", "danger")

# ---------------------------
# Utility functions
# -----------------------------------------------------

def get_individual(short_name):
    """
    Return individual by local name. 
    FAIL-SAFE 2: Uses iterative search for robustness across formats.
    """
    try:
        # 1. Try the standard search by name 
        individual = onto.search_one(name = short_name)
        if individual:
            return individual

        # 2. Fallback: Iterate through all individuals in the world
        for individual in list(onto.individuals()):
            if individual.name == short_name:
                return individual
        
        # 3. Fallback: Search by IRI pattern
        return onto.search_one(iri="*#" + short_name)

    except Exception as e:
        print(f"Error in get_individual for {short_name}: {e}")
        return None

def all_problems():
    """Return list of Problem individuals with error handling."""
    ProblemClass = get_onto_class("Problem")
    if ProblemClass:
        try:
            return list(ProblemClass.instances())
        except Exception as e:
            print(f"Error listing Problem instances: {e}")
            return []
    return []

def all_students():
    """Return list of Student individuals with error handling."""
    StudentClass = get_onto_class("Student")
    if StudentClass:
        try:
            return list(StudentClass.instances())
        except Exception as e:
            print(f"Error listing Student instances: {e}")
            return []
    return []

def all_attempts():
    """Return list of Attempt individuals with error handling."""
    AttemptClass = get_onto_class("Attempt")
    if AttemptClass:
        try:
            return list(AttemptClass.instances())
        except Exception as e:
            print(f"Error listing Attempt instances: {e}")
            return []
    return []

def dims_for_problem(problem):
    
    # Return list of (dim_name, dim_value) pairs for a Problem individual.
    
    dims = []
    try:
        if hasattr(problem, "hasProblemDimension") and problem.hasProblemDimension:
            for d in problem.hasProblemDimension:
                name = d.dimensionName[0] if getattr(d, "dimensionName", None) else ""
                val = d.dimensionValue[0] if getattr(d, "dimensionValue", None) and isinstance(d.dimensionValue, list) else getattr(d, "dimensionValue", None)
                
                # --- FIX 2: Ensure val is a string before being stored in dims list ---
                if val is not None:
                    val = str(val) 
                # ---------------------------------------------------------------------

                dims.append((name, val))
        elif hasattr(problem, "hasDimension") and problem.hasDimension:
            for d in problem.hasDimension:
                name = d.dimensionName[0] if getattr(d, "dimensionName", None) else ""
                val = d.dimensionValue[0] if getattr(d, "dimensionValue", None) and isinstance(d.dimensionValue, list) else getattr(d, "dimensionValue", None)
                
                
                if val is not None:
                    val = str(val)
                # ---------------------------------------------------------------------
                
                dims.append((name, val))
        else:
            
            if getattr(problem, "dimensionValue", None):
                name = problem.dimensionName[0] if getattr(problem, "dimensionName", None) and isinstance(problem.dimensionName, list) else ""
                val = problem.dimensionValue[0] if isinstance(problem.dimensionValue, list) else problem.dimensionValue
                
                
                if val is not None:
                    val = str(val)
                # ---------------------------------------------------------------------

                dims.append((name, val))
    except Exception as e:
        print(f"Error processing dimensions for {problem.name}: {e}")
        flash("Internal error processing problem dimensions.", "danger")
    return dims

def shape_for_problem(problem):
    
    # Return (shape_class_name, shape_individual) for a problem, or (None, None).
    
   
    try:
        if not hasattr(problem, "hasShape") or not problem.hasShape:
            return None, None
        s = problem.hasShape[0]
        
        # 1. Primary Check: Check for specific class types (Triangle, Circle, etc.)
        for c in s.is_a:
            if hasattr(c, "name"):
                cname = c.name
                if cname in ("Circle", "Square", "Rectangle", "Triangle"):
                    return cname, s
        
        # 2. Fallback Check: Use the shape individual's name as a hint 
        # (e.g., if the instance name is 'Triangle_Instance_...')
        if s.name and '_' in s.name:
            # Example: 'Triangle_Instance_Problem_Tri_B3H6' -> 'Triangle'
            name_hint = s.name.split('_')[0]
            if name_hint in ("Circle", "Square", "Rectangle", "Triangle"):
                return name_hint, s

        # 3. Final Fallback: Return the first class name found (might be 'Shape')
        if s.is_a:
            first = s.is_a[0]
            return (first.name if hasattr(first, "name") else None), s
        return None, s
    except Exception as e:
        print(f"Error determining shape for {problem.name}: {e}")
        return None, None

def compute_answer(problem):
    
    # Compute numeric correct answer using shape and dimension values.
    
    
    shape_name, _ = shape_for_problem(problem)
    dims = dims_for_problem(problem)

    def get_val(names):
        """Search dims list for matching names (case-insensitive) and convert value safely."""
        target_names = [x.lower() for x in names] # Create a list of lowercase target names
        
        # 1. Search by name (most accurate)
        for n, v in dims:
            if n and str(n).lower() in target_names:
                try:
                    # Safely convert to float from the string value (v)
                    return float(v) if v is not None else None
                except (ValueError, TypeError):
                    return None # Handle non-numeric dimension values
        
        # 2. Fallback: If only one dimension exists, return it (e.g., Circle, Square)
        if len(dims) == 1:
            try:
                # Safely convert the only dimension value
                return float(dims[0][1]) if dims[0][1] is not None else None
            except (ValueError, TypeError):
                return None
        
                
        return None

    try:
        if shape_name == "Circle":
            r = get_val(["radius", "r"])
            return None if r is None else pi * r * r
        if shape_name == "Square":
            s = get_val(["side", "s"])
            return None if s is None else s * s
        if shape_name == "Rectangle":
            l = get_val(["length", "l"])
            w = get_val(["width", "w"])
            
            # If explicit name match fails, try the first two dimensions in order (Rectangle specific fallback)
            if l is None or w is None:
                if len(dims) >= 2 and dims[0][1] is not None and dims[1][1] is not None:
                    try:
                        l = float(dims[0][1])
                        w = float(dims[1][1])
                    except ValueError:
                        return None
            
            if l is None or w is None:
                return None
            return l * w
            
        if shape_name == "Triangle":
            b = get_val(["base", "b"])
            h = get_val(["height", "h"])
            if b is None or h is None:
                return None
            return 0.5 * b * h
        return None
    except Exception as e:
        print(f"Error during answer computation for {problem.name}: {e}")
        return None

def approx_equal(a, b, rel_tol=0.02, abs_tol=0.05):
    """Compare floats with tolerance (2% or 0.05 default)."""
    try:
        a = float(a); b = float(b)
    except Exception:
        return False
    return abs(a - b) <= max(abs_tol, rel_tol * abs(b))

# ---------------------------
# Flask routes
# -----------------------------------------------------

@app.route("/")
def index():
    problems = all_problems()
    return render_template("index.html", problems=problems)

@app.route("/problem/<name>")
def problem_view(name):
    prob = get_individual(name)
    if prob is None:
        flash(f"Problem '{name}' not found. Check ontology name/file.", "danger")
        return redirect(url_for("index"))
        
    dims = dims_for_problem(prob)
    shape_name, shape_ind = shape_for_problem(prob)
    computed = compute_answer(prob)
    
    # FAIL-SAFE: Handle properties being missing or not lists
    stored = None
    if getattr(prob, "correctAnswer", None):
        try:
            stored = prob.correctAnswer[0] if isinstance(prob.correctAnswer, list) else prob.correctAnswer
        except Exception:
            stored = None # Could not read stored answer

    return render_template("problem.html", problem=prob, dims=dims, shape_name=shape_name,
                             computed=computed, stored=stored)

@app.route("/problem/<name>/submit", methods=["POST"])
def problem_submit(name):
    prob = get_individual(name)
    if prob is None:
        flash(f"Problem '{name}' not found. Cannot submit answer.", "danger")
        return redirect(url_for("index"))

    student_name = request.form.get("student").strip() or "Student_Anonymous"
    answer_text = request.form.get("answer")

    # Input validation
    try:
        answer_val = float(answer_text)
    except Exception:
        flash("Please enter a valid numeric answer.", "warning")
        return redirect(url_for("problem_view", name=name))

    # Compute correct answer
    correct_val = compute_answer(prob)
    if correct_val is None:
        # Fallback to stored answer if computation fails
        stored_answer = getattr(prob, "correctAnswer", None)
        if stored_answer:
            try:
                correct_val = float(stored_answer[0] if isinstance(stored_answer, list) else stored_answer)
            except Exception:
                # This is the original error point. Should be much less frequent now.
                flash("Cannot compute or read correct answer for this problem (check dimensions/shape/stored value).", "danger")
                return redirect(url_for("problem_view", name=name))
        else:
            flash("Cannot compute or read correct answer for this problem (check dimensions/shape).", "danger")
            return redirect(url_for("problem_view", name=name))

    is_correct = approx_equal(answer_val, correct_val)

    # create/get student (FAIL-SAFE: use helper to get class)
    StudentClass = get_onto_class("Student")
    AttemptClass = get_onto_class("Attempt")
    if StudentClass is None or AttemptClass is None:
        return redirect(url_for("problem_view", name=name)) # Error flashed in helper

    student = get_individual(student_name)
    try:
        if student is None:
            student = StudentClass(student_name)
            # Initialize lists safely
            student.studentScore = [0] if not hasattr(student, "studentScore") or student.studentScore is None else student.studentScore
            student.masteryLevel = [0.0] if not hasattr(student, "masteryLevel") or student.masteryLevel is None else student.masteryLevel
            
        # create attempt with unique ID
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        att_name = f"Attempt_{student.name}_{prob.name}_{timestamp}"
        attempt = AttemptClass(att_name)
        
        # Link attempt and set properties (safely)
        if hasattr(attempt, "attemptOf"):
            attempt.attemptOf = [prob]
        if hasattr(attempt, "hasAnswer"):
            attempt.hasAnswer = [answer_val]
        if hasattr(attempt, "isCorrect"):
            attempt.isCorrect = [bool(is_correct)]
        if hasattr(student, "attempts"):
            student.attempts.append(attempt)

        # Update student score and mastery (safely)
        curr_score = student.studentScore[0] if getattr(student, "studentScore", None) else 0
        
        # Safely count attempts including the current one
        num_attempts = len(getattr(student, "attempts", [])) 
        
        if is_correct:
            curr_score += 1
        
        if hasattr(student, "studentScore"):
            student.studentScore = [curr_score]
        if hasattr(student, "masteryLevel"):
            mastery = float(curr_score) / float(max(1, num_attempts))
            student.masteryLevel = [mastery]

        # store problem.correctAnswer if missing
        if getattr(prob, "correctAnswer", None) is None and correct_val is not None and hasattr(prob, "correctAnswer"):
            prob.correctAnswer = [float(correct_val)]

    except Exception as e:
        flash(f"ERROR: Failed to create or link student/attempt individuals: {e}", "danger")
        return redirect(url_for("problem_view", name=name))

    save_ontology()

    if is_correct:
        flash(f"Correct! ✔️ Your answer {answer_val} (expected ≈ {round(correct_val,3)})", "success")
    else:
        flash(f"Incorrect — your answer {answer_val}. Expected ≈ {round(correct_val,3)}", "danger")

    return redirect(url_for("problem_view", name=name))

@app.route("/students")
def students_view():
    studs = all_students()
    # Assuming 'student.html' is the correct name after your fix
    try:
        return render_template("student.html", students=studs) 
    except Exception as e:
        flash(f"ERROR: Failed to render students view (Template name/path error?): {e}", "danger")
        return redirect(url_for("index"))


@app.route("/attempts")
def attempts_view():
    attempts = all_attempts()
    return render_template("attempts.html", attempts=attempts)

@app.route("/add_problem", methods=["GET", "POST"])
def add_problem():
    """Add a new problem dynamically."""
    if request.method == "POST":
        name = request.form.get("problem_name", "").strip()
        shape = request.form.get("shape")
        d1_value = request.form.get("dim1_value", "").strip()
        
        # Initial validation
        if not name or not shape or not d1_value:
            flash("Provide problem name, shape, and at least the first dimension value.", "warning")
            return redirect(url_for("add_problem"))

        if get_individual(name) is not None:
            flash("A problem with that name already exists. Pick another unique name.", "warning")
            return redirect(url_for("add_problem"))

        # Get necessary classes (FAIL-SAFE: use helper)
        ProblemClass = get_onto_class("Problem")
        DimensionClass = get_onto_class("Dimension")
        if ProblemClass is None or DimensionClass is None:
             return redirect(url_for("add_problem")) # Error flashed in helper

        # --- Create Individuals ---
        try:
            prob = ProblemClass(name)
            
            # Create Shape Instance
            shape_class = getattr(onto, shape, None)
            if shape_class is None:
                flash(f"Unknown shape class '{shape}'. Check ontology.", "danger")
                return redirect(url_for("add_problem"))

            shape_inst_name = f"{shape}_inst_{name}"
            shape_inst = shape_class(shape_inst_name)
            
            # Link problem -> shape
            if hasattr(prob, "hasShape"):
                prob.hasShape = [shape_inst]

            # Dimension 1 Setup
            d1_name = request.form.get("dim1_name", "").strip()
            d1_id = f"{name}_dim1"
            d1 = DimensionClass(d1_id)
            if hasattr(d1, "dimensionName"):
                d1.dimensionName = [d1_name or "dim1"]
            if hasattr(d1, "dimensionValue"):
                d1.dimensionValue = [float(d1_value)] # Value already validated as non-empty above

            # Link dimension 1
            if hasattr(prob, "hasProblemDimension"):
                prob.hasProblemDimension = [d1]
            elif hasattr(prob, "hasDimension"):
                prob.hasDimension = [d1]

            # Dimension 2 Setup (if present)
            d2_value = request.form.get("dim2_value", "").strip()
            if d2_value:
                d2_name = request.form.get("dim2_name", "").strip()
                d2_id = f"{name}_dim2"
                d2 = DimensionClass(d2_id)
                if hasattr(d2, "dimensionName"):
                    d2.dimensionName = [d2_name or "dim2"]
                if hasattr(d2, "dimensionValue"):
                    d2.dimensionValue = [float(d2_value)]
                
                # Link dimension 2
                if hasattr(prob, "hasProblemDimension"):
                    prob.hasProblemDimension.append(d2)
                elif hasattr(prob, "hasDimension"):
                    prob.hasDimension.append(d2)

            # compute and attach correctAnswer
            correct_val = compute_answer(prob)
            if correct_val is not None and hasattr(prob, "correctAnswer"):
                prob.correctAnswer = [float(correct_val)]
            
        except ValueError:
            flash("ERROR: Dimension values must be valid numbers.", "danger")
            return redirect(url_for("add_problem"))
        except Exception as e:
            flash(f"ERROR: Failed to create ontology individuals: {e}", "danger")
            return redirect(url_for("add_problem"))

        save_ontology()
        flash(f"Problem {name} created.", "success")
        return redirect(url_for("problem_view", name=name))

    return render_template("add_problem.html")

# ---------------------------
# Run
# ---------------------------
if __name__ == "__main__":
    app.run(debug=True)