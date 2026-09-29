"""Country-aware territorial catalog for patient residence (additive)."""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

revision = "0031_country_territory"
down_revision = "0030_patient_demographics"
branch_labels = None
depends_on = None

PROVINCES = [
    ("01", "Distrito Nacional"), ("02", "Azua"), ("03", "Baoruco"), ("04", "Barahona"), ("05", "Dajabón"), ("06", "Duarte"), ("07", "Elías Piña"), ("08", "El Seibo"), ("09", "Espaillat"), ("10", "Independencia"), ("11", "La Altagracia"), ("12", "La Romana"), ("13", "La Vega"), ("14", "María Trinidad Sánchez"), ("15", "Monte Cristi"), ("16", "Pedernales"), ("17", "Peravia"), ("18", "Puerto Plata"), ("19", "Hermanas Mirabal"), ("20", "Samaná"), ("21", "San Cristóbal"), ("22", "San Juan"), ("23", "San Pedro de Macorís"), ("24", "Sánchez Ramírez"), ("25", "Santiago"), ("26", "Santiago Rodríguez"), ("27", "Valverde"), ("28", "Monseñor Nouel"), ("29", "Monte Plata"), ("30", "Hato Mayor"), ("31", "San José de Ocoa"), ("32", "Santo Domingo"),
]
# República Dominicana: 32 provincial units and 158 municipalities. The source
# is ONE División Territorial 2020 (edition 2021); names are versioned here so
# subsequent official releases change catalog rows rather than patient columns.
MUNICIPALITIES = {
    "01": ['Santo Domingo de Guzmán'],
    "02": ['Azua de Compostela', 'Estebanía', 'Guayabal', 'Las Charcas', 'Las Yayas de Viajama', 'Padre Las Casas', 'Peralta', 'Pueblo Viejo', 'Sabana Yegua', 'Tábara Arriba'],
    "03": ['Galván', 'Los Ríos', 'Neiba', 'Tamayo', 'Villa Jaragua'],
    "04": ['Barahona', 'Cabral', 'El Peñón', 'Enriquillo', 'Fundación', 'Jaquimeyes', 'La Ciénaga', 'Las Salinas', 'Paraíso', 'Polo', 'Vicente Noble'],
    "05": ['Dajabón', 'El Pino', 'Loma de Cabrera', 'Partido', 'Restauración'],
    "06": ['Arenoso', 'Castillo', 'Eugenio María de Hostos', 'Las Guáranas', 'Pimentel', 'San Francisco de Macorís', 'Villa Riva'],
    "07": ['Bánica', 'Comendador', 'El Llano', 'Hondo Valle', 'Juan Santiago', 'Pedro Santana'],
    "08": ['El Seibo', 'Miches'],
    "09": ['Cayetano Germosén', 'Gaspar Hernández', 'Jamao al Norte', 'Moca', 'San Víctor'],
    "10": ['Cristóbal', 'Duvergé', 'Jimaní', 'La Descubierta', 'Mella', 'Postrer Río'],
    "11": ['Higüey', 'San Rafael del Yuma'],
    "12": ['Guaymate', 'La Romana', 'Villa Hermosa'],
    "13": ['Constanza', 'Jarabacoa', 'Jima Abajo', 'La Concepción de La Vega'],
    "14": ['Cabrera', 'El Factor', 'Nagua', 'Río San Juan'],
    "15": ['Castañuela', 'Guayubín', 'Las Matas de Santa Cruz', 'Montecristi', 'Pepillo Salcedo', 'Villa Vásquez'],
    "16": ['Oviedo', 'Pedernales'],
    "17": ['Baní', 'Matanzas', 'Nizao'],
    "18": ['Altamira', 'Guananico', 'Imbert', 'Los Hidalgos', 'Luperón', 'Puerto Plata', 'Sosúa', 'Villa Isabela', 'Villa Montellano'],
    "19": ['Salcedo', 'Tenares', 'Villa Tapia'],
    "20": ['Las Terrenas', 'Samaná', 'Sánchez'],
    "21": ['Bajos de Haina', 'Cambita Garabito', 'Los Cacaos', 'Sabana Grande de Palenque', 'San Cristóbal', 'San Gregorio de Nigua', 'Villa Altagracia', 'Yaguate'],
    "22": ['Bohechío', 'El Cercado', 'Juan de Herrera', 'Las Matas de Farfán', 'San Juan de la Maguana', 'Vallejuelo'],
    "23": ['Consuelo', 'Guayacanes', 'Quisqueya', 'Ramón Santana', 'San José de Los Llanos', 'San Pedro de Macorís'],
    "24": ['Cevicos', 'Cotuí', 'Fantino', 'La Mata'],
    "25": ['Baitoa', 'Bisonó', 'Jánico', 'Licey al Medio', 'Puñal', 'Sabana Iglesia', 'San José de las Matas', 'Santiago', 'Tamboril', 'Villa González'],
    "26": ['Los Almácigos', 'Monción', 'San Ignacio de Sabaneta'],
    "27": ['Esperanza', 'Laguna Salada', 'Mao'],
    "28": ['Bonao', 'Maimón', 'Piedra Blanca'],
    "29": ['Bayaguana', 'Monte Plata', 'Peralvillo', 'Sabana Grande de Boyá', 'Yamasá'],
    "30": ['El Valle', 'Hato Mayor del Rey', 'Sabana de la Mar'],
    "31": ['Rancho Arriba', 'Sabana Larga', 'San José de Ocoa'],
    "32": ['Boca Chica', 'Los Alcarrizos', 'Pedro Brand', 'San Antonio de Guerra', 'Santo Domingo Este', 'Santo Domingo Norte', 'Santo Domingo Oeste'],
}


def upgrade():
    seed_time = datetime.now(timezone.utc).replace(tzinfo=None)
    op.create_table("countries", sa.Column("code", sa.String(2), primary_key=True), sa.Column("name", sa.String(100), nullable=False, unique=True), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_countries_name", "countries", ["name"])
    op.create_index("ix_countries_is_active", "countries", ["is_active"])
    op.create_table("territorial_levels", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("country_code", sa.String(2), sa.ForeignKey("countries.code", ondelete="RESTRICT"), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.Column("key", sa.String(50), nullable=False), sa.Column("display_label", sa.String(100), nullable=False), sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.UniqueConstraint("country_code", "position", name="uq_territorial_levels_country_position"))
    op.create_index("ix_territorial_levels_country_code", "territorial_levels", ["country_code"])
    op.create_table("territorial_units", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("country_code", sa.String(2), sa.ForeignKey("countries.code", ondelete="RESTRICT"), nullable=False), sa.Column("territorial_level_id", sa.Integer(), sa.ForeignKey("territorial_levels.id", ondelete="RESTRICT"), nullable=False), sa.Column("parent_id", sa.Integer(), sa.ForeignKey("territorial_units.id", ondelete="RESTRICT"), nullable=True), sa.Column("code", sa.String(30), nullable=True), sa.Column("name", sa.String(150), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.UniqueConstraint("country_code", "territorial_level_id", "parent_id", "name", name="uq_territorial_units_path_name"))
    op.create_index("ix_territorial_units_country_code", "territorial_units", ["country_code"])
    op.create_index("ix_territorial_units_territorial_level_id", "territorial_units", ["territorial_level_id"])
    op.create_index("ix_territorial_units_parent_id", "territorial_units", ["parent_id"])
    op.create_table("regional_settings", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("default_country_code", sa.String(2), sa.ForeignKey("countries.code", ondelete="RESTRICT"), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.bulk_insert(sa.table("countries", sa.column("code", sa.String), sa.column("name", sa.String), sa.column("is_active", sa.Boolean), sa.column("created_at", sa.DateTime)), [{"code":"DO", "name":"República Dominicana", "is_active":True, "created_at":seed_time}])
    op.bulk_insert(sa.table("territorial_levels", sa.column("id", sa.Integer), sa.column("country_code", sa.String), sa.column("position", sa.Integer), sa.column("key", sa.String), sa.column("display_label", sa.String), sa.column("is_required", sa.Boolean), sa.column("is_active", sa.Boolean)), [{"id":1,"country_code":"DO","position":1,"key":"province","display_label":"Provincia","is_required":True,"is_active":True},{"id":2,"country_code":"DO","position":2,"key":"municipality","display_label":"Municipio","is_required":True,"is_active":True}])
    op.bulk_insert(sa.table("territorial_units", sa.column("id", sa.Integer), sa.column("country_code", sa.String), sa.column("territorial_level_id", sa.Integer), sa.column("parent_id", sa.Integer), sa.column("code", sa.String), sa.column("name", sa.String), sa.column("is_active", sa.Boolean)), [{"id":i,"country_code":"DO","territorial_level_id":1,"parent_id":None,"code":code,"name":name,"is_active":True} for i,(code,name) in enumerate(PROVINCES,1)])
    province_ids = {code:i for i,(code,_) in enumerate(PROVINCES,1)}
    rows=[]; next_id=100
    for code,names in MUNICIPALITIES.items():
        for index,name in enumerate(names,1):
            rows.append({"id":next_id,"country_code":"DO","territorial_level_id":2,"parent_id":province_ids[code],"code":f"{code}-{index:02d}","name":name,"is_active":True}); next_id += 1
    op.bulk_insert(sa.table("territorial_units", sa.column("id", sa.Integer), sa.column("country_code", sa.String), sa.column("territorial_level_id", sa.Integer), sa.column("parent_id", sa.Integer), sa.column("code", sa.String), sa.column("name", sa.String), sa.column("is_active", sa.Boolean)), rows)
    op.bulk_insert(sa.table("regional_settings", sa.column("id", sa.Integer), sa.column("default_country_code", sa.String), sa.column("updated_at", sa.DateTime)), [{"id":1,"default_country_code":"DO","updated_at":seed_time}])
    with op.batch_alter_table("patients") as batch:
        batch.add_column(sa.Column("country_code", sa.String(2), nullable=True))
        batch.add_column(sa.Column("territorial_unit_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("sector_locality", sa.String(150), nullable=True))
        batch.create_foreign_key("fk_patients_country_code", "countries", ["country_code"], ["code"])
        batch.create_foreign_key("fk_patients_territorial_unit_id", "territorial_units", ["territorial_unit_id"], ["id"])
        batch.create_index("ix_patients_country_code", ["country_code"])
        batch.create_index("ix_patients_territorial_unit_id", ["territorial_unit_id"])


def downgrade():
    with op.batch_alter_table("patients") as batch:
        batch.drop_index("ix_patients_territorial_unit_id")
        batch.drop_index("ix_patients_country_code")
        batch.drop_constraint("fk_patients_territorial_unit_id", type_="foreignkey")
        batch.drop_constraint("fk_patients_country_code", type_="foreignkey")
        batch.drop_column("sector_locality")
        batch.drop_column("territorial_unit_id")
        batch.drop_column("country_code")
    op.drop_table("regional_settings")
    op.drop_index("ix_territorial_units_parent_id", table_name="territorial_units")
    op.drop_index("ix_territorial_units_territorial_level_id", table_name="territorial_units")
    op.drop_index("ix_territorial_units_country_code", table_name="territorial_units")
    op.drop_table("territorial_units")
    op.drop_index("ix_territorial_levels_country_code", table_name="territorial_levels")
    op.drop_table("territorial_levels")
    op.drop_index("ix_countries_is_active", table_name="countries")
    op.drop_index("ix_countries_name", table_name="countries")
    op.drop_table("countries")
