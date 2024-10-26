from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
import bcrypt
from sqlalchemy import inspect

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///school.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.secret_key = os.urandom(24)  # Altere para uma chave secreta mais forte em produção
db = SQLAlchemy(app)

# Inicialização do Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

# Modelo de Usuário
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # 'professor' ou 'aluno'

# Modelo para Favoritos
class Favorito(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    turma_id = db.Column(db.Integer, db.ForeignKey('turma.id'))

    aluno = db.relationship('User', backref='favoritos')
    turma = db.relationship('Turma', backref='favoritos')

# Modelos para Professores, Turmas e Materiais
class Professor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    turmas = db.relationship('Turma', backref='professor', lazy=True)

class Turma(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    professor_id = db.Column(db.Integer, db.ForeignKey('professor.id'))
    materials = db.relationship('Material', backref='turma', lazy=True)

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100))
    tipo = db.Column(db.String(50))  # Tipo de material (PDF, Vídeo, Outro)
    turma_id = db.Column(db.Integer, db.ForeignKey('turma.id'))

# Funções adicionais
from editor_materiais import editar_material  # Importa a função de editar materiais
from mensagens import enviar_mensagem          # Importa a função de enviar mensagens
from busca import buscar_turmas                # Importa a função de buscar turmas

# Rota para a página inicial
@app.route('/')
def index():
    return render_template('index.html')

# Rota de registro com confirmação de senha
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('role')

        if password != confirm_password:
            flash('As senhas não coincidem!', 'error')
            return redirect(url_for('register'))

        # Verificar se o usuário já existe
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Usuário já existe. Escolha outro nome de usuário.', 'error')
            return redirect(url_for('register'))

        # Criar novo usuário com bcrypt
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        new_user = User(username=username, password=hashed, role=role)
        db.session.add(new_user)
        db.session.commit()

        flash('Registro concluído! Você pode fazer login agora.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# Rota de login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
            login_user(user)
            return redirect(url_for('professor_page' if user.role == 'professor' else 'aluno_page'))
        
        flash('Nome de usuário ou senha incorretos.', 'error')

    return render_template('login.html')

# Rota para a página do professor
@app.route('/professor', methods=['GET', 'POST'])
@login_required
def professor_page():
    if current_user.role != 'professor':
        flash('Acesso negado!', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Criar nova turma
        class_name = request.form.get('class_name')
        if class_name:
            new_class = Turma(name=class_name, professor_id=current_user.id)
            db.session.add(new_class)
            db.session.commit()
            flash('Turma criada com sucesso!', 'success')

    page = request.args.get('page', 1, type=int)
    turmas = Turma.query.filter_by(professor_id=current_user.id).paginate(page=page, per_page=5)  # Paginação

    return render_template('professor.html', turmas=turmas)

# Rota para upload de arquivos
@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if request.method == 'POST':
        file = request.files.get('file')
        turma_id = request.form.get('turma')  # ID da turma
        tipo = request.form.get('tipo')  # Tipo de material
        
        if not turma_id:
            flash("Erro: O campo 'turma' não foi enviado", 'error')
            return redirect(url_for('professor_page'))
        
        if file:
            try:
                filename = file.filename
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                new_material = Material(filename=filename, tipo=tipo, turma_id=turma_id)
                db.session.add(new_material)
                db.session.commit()
                flash('Material enviado com sucesso!', 'success')
            except Exception as e:
                flash(f'Erro ao enviar o material: {str(e)}', 'error')
        else:
            flash('Nenhum arquivo selecionado.', 'error')
    
    return redirect(url_for('professor_page'))

# Rota para a página de alunos
@app.route('/aluno', methods=['GET'])
@login_required
def aluno_page():
    if current_user.role != 'aluno':
        flash('Acesso negado!', 'error')
        return redirect(url_for('index'))

    # Buscar todas as turmas
    page = request.args.get('page', 1, type=int)
    turmas = Turma.query.paginate(page=page, per_page=5)  # Paginação

    return render_template('aluno.html', turmas=turmas)

# Rota para listar turmas favoritas
@app.route('/favoritas', methods=['GET'])
@login_required
def favoritas_page():
    if current_user.role != 'aluno':
        flash('Acesso negado!', 'error')
        return redirect(url_for('index'))

    # Buscar turmas favoritas
    turmas_favoritas = Favorito.query.filter_by(aluno_id=current_user.id).all()
    favoritas_ids = [favorito.turma_id for favorito in turmas_favoritas]
    
    # Verificar se existem turmas favoritas
    if favoritas_ids:
        turmas = Turma.query.filter(Turma.id.in_(favoritas_ids)).paginate(page=request.args.get('page', 1, type=int), per_page=5)
    else:
        turmas = []  # Caso não haja turmas favoritas

    return render_template('favoritas.html', turmas=turmas)

# Rota para favoritar turmas
@app.route('/favoritar/<int:turma_id>', methods=['POST'])
@login_required
def favoritar_turma(turma_id):
    if current_user.role != 'aluno':
        flash('Acesso negado!', 'error')
        return redirect(url_for('index'))

    favorito_existente = Favorito.query.filter_by(aluno_id=current_user.id, turma_id=turma_id).first()
    if favorito_existente:
        flash('Você já favoritou esta turma.', 'error')
    else:
        favorito = Favorito(aluno_id=current_user.id, turma_id=turma_id)
        db.session.add(favorito)
        db.session.commit()
        flash('Turma favoritada com sucesso!', 'success')
        
    return redirect(url_for('aluno_page'))

# Rota para exibir uma turma específica
@app.route('/turma/<nome>', methods=['GET'])
@login_required
def turma_page(nome):
    turma = Turma.query.filter_by(name=nome).first()
    if not turma:
        flash('Turma não encontrada.', 'error')
        return redirect(url_for('aluno_page'))

    materiais = Material.query.filter_by(turma_id=turma.id).all()
    return render_template('turma.html', turma=turma, materiais=materiais)

# Rota para editar materiais
@app.route('/editar_material/<int:id>', methods=['POST'])
@login_required
def editar_material_route(id):
    material = Material.query.get(id)
    if not material:
        flash('Material não encontrado.', 'error')
        return redirect(url_for('professor_page'))
    
    # Chamar função para editar o material
    novo_nome = request.form.get('novo_nome')
    tipo = request.form.get('tipo')
    
    editar_material(material, novo_nome, tipo)
    db.session.commit()
    
    flash('Material editado com sucesso!', 'success')
    return redirect(url_for('professor_page'))

# Rota para enviar mensagem
@app.route('/enviar_mensagem', methods=['POST'])
@login_required
def enviar_mensagem_route():
    destinatario = request.form.get('destinatario')
    mensagem = request.form.get('mensagem')
    
    enviar_mensagem(destinatario, mensagem)
    
    flash('Mensagem enviada com sucesso!', 'success')
    return redirect(url_for('professor_page'))

# Rota para buscar turmas
@app.route('/buscar_turmas', methods=['GET'])
@login_required
def buscar_turmas_route():
    nome_turma = request.args.get('nome_turma')
    
    turmas_encontradas = buscar_turmas(nome_turma)
    
    return render_template('turmas_encontradas.html', turmas=turmas_encontradas)

# Rota de logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

if __name__ == '__main__':
    app.run(debug=True)
