import psycopg2
from .db import engine
from .views import app
from wtforms import Form, StringField, SelectField, validators
from wtforms.fields import EmailField
from wtforms.validators import ValidationError

VALID_COUNTRIES = [
    ('',''), # Optional empty choice
    ('usa', 'USA'),
    ('canada', 'Canada'),
    ('portugal', 'Portugal'),
    ('uk', 'UK'),
    ('germany', 'Germany'),
    ('mexico', 'Mexico')
]
FORM_KEYS = ['firstname', 'lastname', 'expert', 'email', 'phone', 'country']

class ShifterInfoForm(Form):
    def validate_phone(form, field):
        if len(field.data) != 11 and len(field.data) != 12:
            raise ValidationError("Phone number wrong length")
        if field.data and not str(field.data).isdigit():
            raise ValidationError("Phone number must contain only digits")

    firstname = StringField('First Name', [validators.DataRequired()])
    lastname = StringField('Last Name', [validators.DataRequired()])
    expert = SelectField('Expert', choices=[])
    email = EmailField('Email', [validators.Optional(), validators.Email()])
    phone = StringField('Phone', [validators.Optional()])
    country = SelectField('Country', choices=VALID_COUNTRIES)

def get_experts():
    """
    Returns a list of the names of all on-call experts.
    """
    conn = engine.connect()
    result = conn.execute("SELECT firstname, lastname FROM experts")
    row = result.fetchall()
    names = []
    for first, last in row:
        name = first + " " + last
        names.append((name, name))

    return names

def get_shifter_information():
    """
    Get some of the information about the current shifter.

    Returns the first/last name of the current shifter and the first name of
    the on-call expert.
    """
    conn = engine.connect()

    result = conn.execute("SELECT firstname, lastname, email, phonenumber, expert "
                          "FROM current_shifter_information")

    row = result.fetchone()
    if row is None:
        return None, None, None

    email = row[2]
    phone = row[3]

    if len(email) and len(phone):
         updates = "Receiving both email and text alerts."
    elif len(email):
        updates = "Receiving only email alerts."
    elif len(phone):
        updates = "Receiving only text alerts."
    else:
        updates = "Receiving neither text or email alerts."

    shifter = ""
    expert = ""

    shifter_firstname = row[0]
    shifter_lastname = row[1]
    if shifter_firstname and shifter_lastname:
        shifter = "Current shifter: %s %s" % \
                  (shifter_firstname.capitalize(), shifter_lastname.capitalize())

    expert_name = row[4]
    if expert_name:
        first = expert_name.split()[0]
        last = expert_name.split()[1]
        expert  = "Current expert: %s %s" % (first, last)

    return shifter, expert, updates

def set_shifter_information(form):
    """
    Update the database with the current shift information.
    """
    conn = psycopg2.connect(dbname=app.config['DB_NAME'],
                            user=app.config['DB_OPERATOR'],
                            host=app.config['DB_HOST'],
                            password=app.config['DB_OPERATOR_PASS'])
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

    cursor = conn.cursor()

    result = cursor.execute("INSERT INTO shifter_information (firstname, "
                 "lastname, phonenumber, email, country, expert) "
                 "VALUES (%(firstname)s, %(lastname)s, %(phone)s, "
                 "%(email)s, %(country)s, %(expert)s)", form.data)
