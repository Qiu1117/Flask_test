from flask import (
    jsonify,
    request,
    Blueprint,
)
from datetime import datetime, timedelta
import math
from middleware import token_required, permission_check
from db_models import (
    db,
    Account,
    Group,
    Acc_Group,
    Dataset_Group,
    Dataset,
    Patient,
    Study,
    Series,
    Dataset_Patients,
    Dataset_Studies,
    Dataset_Series,
    Dataset_Instances,
)
from sqlalchemy.orm import aliased
from sqlalchemy import update, text, func, and_, or_
import requests
import config

dashboard = Blueprint("dashboard", __name__)



def orthanc_request(method, endpoint, **kwargs):
    url = f"{config.ORTHANC_URL}/{endpoint.lstrip('/')}"
    auth = (config.ORTHANC_USERNAME, config.ORTHANC_PASSWORD)
    
    # 如果没有指定auth参数，添加默认认证
    if 'auth' not in kwargs:
        kwargs['auth'] = auth
        
    return requests.request(method, url, **kwargs)


# ------------------------------------------ Card Info --------------------------------------
@dashboard.route("/dashboard_databaseinfo_card", methods=["GET"])
@token_required()
def get_database_info():
    dataset_count = get_dataset_count()
    group_count = get_group_count()
    patient_count = get_patient_count()
    instance_count = get_instance_count()

    result = {
        "Datasets": dataset_count,
        "Groups": group_count,
        "Patients": patient_count,
        "Instances": instance_count
    }

    return jsonify(result)

def get_dataset_count():
    return Dataset.query.filter_by(valid=True).count()

def get_group_count():
    return Group.query.filter_by(valid=True).count()

def get_patient_count():
    return Patient.query.filter_by(valid=True).count()

def get_instance_count():
    return db.session.query(func.count(Dataset_Instances.instance_orthanc_id.distinct())).scalar()



@dashboard.route("/dashboard_orthancinfo_card", methods=["GET"])
@token_required()
def get_orthanc_stats():
    response = orthanc_request("GET", "statistics")

    if response.status_code == 200:
        orthanc_stats = response.json()

        stats = {
            "Patient": orthanc_stats["CountPatients"],
            "Study": orthanc_stats["CountStudies"],
            "Series": orthanc_stats["CountSeries"],
            "Instance": orthanc_stats["CountInstances"],
        }

        return jsonify(stats), 200
    else:
        return (
            jsonify({"error": "Failed to retrieve statistics from Orthanc"}),
            response.status_code,
        )


@dashboard.route("/dashboard_datasetinfo", methods=["GET"])
@token_required()
def get_dataset_info():
    dataset_id = request.args.get('dataset_id', type=int)
    if not dataset_id:
        return jsonify({"error": "Dataset ID is required"}), 400

    # 获取数据集信息
    dataset = Dataset.query.get(dataset_id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    modalities = dataset.modalities if dataset.modalities else []

    patient_count = db.session.query(func.count(Dataset_Patients.patient_orthanc_id.distinct())).\
        filter(Dataset_Patients.dataset_id == dataset_id, Dataset_Patients.valid == True).scalar()

    study_count = db.session.query(func.count(Dataset_Studies.study_orthanc_id.distinct())).\
        filter(Dataset_Studies.dataset_id == dataset_id, Dataset_Studies.valid == True).scalar()

    series_count = db.session.query(func.count(Dataset_Series.series_orthanc_id.distinct())).\
        filter(Dataset_Series.dataset_id == dataset_id, Dataset_Series.valid == True).scalar()

    instance_count = db.session.query(func.count(Dataset_Instances.instance_orthanc_id.distinct())).\
        join(Dataset_Series, Dataset_Series.series_orthanc_id == Dataset_Instances.series_orthanc_id).\
        filter(Dataset_Series.dataset_id == dataset_id, Dataset_Series.valid == True).scalar()

    result = {
        "Modality": modalities,
        "Patient": patient_count,
        "Study": study_count,
        "Series": series_count,
        "Instance": instance_count
    }

    return jsonify(result)


@dashboard.route("/dashboard_dataset_info", methods=["GET"])
def get_dashboard_dataset_info():
    dataset_id = request.args.get("dataset_id")

    if dataset_id:
        patients = (
            db.session.query(func.count(Dataset_Patients.patient_orthanc_id.distinct()))
            .filter(
                Dataset_Patients.dataset_id == dataset_id,
                Dataset_Patients.valid == True,
            )
            .scalar()
        )

        studies = (
            db.session.query(func.count(Dataset_Studies.study_orthanc_id.distinct()))
            .filter(
                Dataset_Studies.dataset_id == dataset_id, Dataset_Studies.valid == True
            )
            .scalar()
        )

        series = (
            db.session.query(func.count(Dataset_Series.series_orthanc_id.distinct()))
            .filter(
                Dataset_Series.dataset_id == dataset_id, Dataset_Series.valid == True
            )
            .scalar()
        )

        DS = aliased(Dataset_Series)
        instances = (
            db.session.query(
                func.count(Dataset_Instances.instance_orthanc_id.distinct())
            )
            .join(DS, DS.series_orthanc_id == Dataset_Instances.series_orthanc_id)
            .filter(
                DS.dataset_id == dataset_id,
                DS.valid == True,
                Dataset_Instances.status == 0,  # 假设 0 表示有效
            )
            .scalar()
        )

    else:
        patients = (
            db.session.query(func.count(Dataset_Patients.patient_orthanc_id.distinct()))
            .filter(Dataset_Patients.valid == True)
            .scalar()
        )

        studies = (
            db.session.query(func.count(Dataset_Studies.study_orthanc_id.distinct()))
            .filter(Dataset_Studies.valid == True)
            .scalar()
        )

        series = (
            db.session.query(func.count(Dataset_Series.series_orthanc_id.distinct()))
            .filter(Dataset_Series.valid == True)
            .scalar()
        )

        instances = (
            db.session.query(
                func.count(Dataset_Instances.instance_orthanc_id.distinct())
            )
            .filter(Dataset_Instances.status == 0)  # 假设 0 表示有效
            .scalar()
        )

    return jsonify(
        {"patient": patients, "study": studies, "series": series, "instance": instances}
    )


# ------------------------------------------ Bar Chart --------------------------------------
@dashboard.route("/dashboard_patient_count", methods=["GET"])
def get_alldataset_patient_count():
    try:
        query = (
            db.session.query(
                Dataset.id,
                Dataset.dataset_name,
                func.count(Dataset_Patients.patient_orthanc_id.distinct()).label(
                    "patient_count"
                ),
            )
            .join(Dataset_Patients, Dataset.id == Dataset_Patients.dataset_id)
            .filter(Dataset.valid == True, Dataset_Patients.valid == True)
            .group_by(Dataset.id, Dataset.dataset_name)
            .all()
        )

        result = {
            dataset_name: patient_count for _, dataset_name, patient_count in query
        }

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dashboard.route("/dashboard_study_count", methods=["GET"])
def get_alldataset_study_count():
    try:
        query = (
            db.session.query(
                Dataset.id,
                Dataset.dataset_name,
                func.count(Dataset_Studies.study_orthanc_id.distinct()).label(
                    "study_count"
                ),
            )
            .join(Dataset_Studies, Dataset.id == Dataset_Studies.dataset_id)
            .filter(Dataset.valid == True, Dataset_Studies.valid == True)
            .group_by(Dataset.id, Dataset.dataset_name)
            .all()
        )

        result = {dataset_name: study_count for _, dataset_name, study_count in query}

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dashboard.route("/dashboard_series_count", methods=["GET"])
def get_alldataset_series_count():
    try:
        query = (
            db.session.query(
                Dataset.id,
                Dataset.dataset_name,
                func.count(Dataset_Series.series_orthanc_id.distinct()).label(
                    "series_count"
                ),
            )
            .join(Dataset_Series, Dataset.id == Dataset_Series.dataset_id)
            .filter(Dataset.valid == True, Dataset_Series.valid == True)
            .group_by(Dataset.id, Dataset.dataset_name)
            .all()
        )

        result = {dataset_name: series_count for _, dataset_name, series_count in query}

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dashboard.route("/dashboard_dataset_age_distribution", methods=["GET"])
def get_age_distribution():
    dataset_id = request.args.get("dataset_id", type=int)
    try:
        current_year = datetime.now().year

        query = (
            db.session.query(Patient.patient_birthdate)
            .join(Dataset_Patients, Dataset_Patients.patient_orthanc_id == Patient.patient_orthanc_id)
            .filter(Dataset_Patients.dataset_id == dataset_id)
            .filter(Dataset_Patients.valid == True, Patient.valid == True)
            .all()
        )

        age_groups = {}
        total_patients = 0

        for (birthdate,) in query:
            if (
                birthdate and len(birthdate) == 8
            ):  
                birth_year = int(birthdate[:4])
                age = current_year - birth_year
                group = math.floor(age / 10) * 10
                age_groups[group] = age_groups.get(group, 0) + 1
                total_patients += 1

        age_distribution = {
            f"{group}-{group+9}": count for group, count in age_groups.items()
        }

        sorted_distribution = dict(
            sorted(age_distribution.items(), key=lambda x: int(x[0].split("-")[0]))
        )

        return jsonify(sorted_distribution)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dashboard.route("/dashboard_dataset_weight_distribution", methods=["GET"])
def get_weight_distribution():
    dataset_id = request.args.get("dataset_id", type=int)
    try:
        query = (
            db.session.query(Patient.patient_weight)
            .join(
                Dataset_Patients,
                Dataset_Patients.patient_orthanc_id == Patient.patient_orthanc_id,
            )
            .filter(Dataset_Patients.dataset_id == dataset_id)
            .filter(Dataset_Patients.valid == True, Patient.valid == True)
            .filter(Patient.patient_weight.isnot(None))
            .all()
        )

        weight_groups = {}
        total_patients = 0

        for (weight,) in query:
            if weight:
                group = (
                    math.floor(weight / 10) * 10
                )  # Group weights into 10 kg intervals
                weight_groups[group] = weight_groups.get(group, 0) + 1
                total_patients += 1

        weight_distribution = {
            f"{group}-{group+9}": count for group, count in weight_groups.items()
        }

        sorted_distribution = dict(
            sorted(weight_distribution.items(), key=lambda x: int(x[0].split("-")[0]))
        )

        return jsonify(sorted_distribution)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dashboard.route("/dashboard_alldataset_gender_count", methods=["GET"])
def get_alldataset_gender_count():
    try:
        query = (
            db.session.query(
                Dataset.id,
                Dataset.dataset_name,
                Patient.patient_sex,
                func.count(Patient.patient_orthanc_id.distinct()).label(
                    "patient_count"
                ),
            )
            .join(Dataset_Patients, Dataset.id == Dataset_Patients.dataset_id)
            .join(
                Patient,
                Dataset_Patients.patient_orthanc_id == Patient.patient_orthanc_id,
            )
            .filter(
                Dataset.valid == True,
                Dataset_Patients.valid == True,
                Patient.valid == True,
            )
            .group_by(Dataset.id, Dataset.dataset_name, Patient.patient_sex)
            .all()
        )

        result = {}
        for dataset_id, dataset_name, sex, count in query:
            if dataset_name not in result:
                result[dataset_name] = {"Male": 0, "Female": 0}
            if sex == "M":
                result[dataset_name]["Male"] = count
            elif sex == "F":
                result[dataset_name]["Female"] = count

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dashboard.route("/dashboard_alldataset_scan_manufacturer_count", methods=["GET"])
def get_dataset_scan_manufacturer_count():
    try:
        query = (
            db.session.query(
                Dataset.id,
                Dataset.dataset_name,
                Series.manufacturer,
                func.count(Series.series_orthanc_id.distinct()).label("scan_count"),
            )
            .join(Dataset_Series, Dataset.id == Dataset_Series.dataset_id)
            .join(Series, Dataset_Series.series_orthanc_id == Series.series_orthanc_id)
            .filter(
                Dataset.valid == True,
                Dataset_Series.valid == True,
                Series.valid == True,
                Series.manufacturer.isnot(None),
            )
            .group_by(Dataset.id, Dataset.dataset_name, Series.manufacturer)
            .all()
        )

        result = {}
        for dataset_id, dataset_name, manufacturer, count in query:
            if dataset_name not in result:
                result[dataset_name] = {}
            result[dataset_name][manufacturer] = count

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------------------------------ Pie Chart --------------------------------------
@dashboard.route("/dashboard_patient_gender_count", methods=["GET"])
def get_alldataset_gender_count4pie():
    try:
        query = (
            db.session.query(
                Dataset.id,
                Dataset.dataset_name,
                Patient.patient_sex,
                func.count(Patient.patient_orthanc_id.distinct()).label(
                    "patient_count"
                ),
            )
            .join(Dataset_Patients, Dataset.id == Dataset_Patients.dataset_id)
            .join(
                Patient,
                Dataset_Patients.patient_orthanc_id == Patient.patient_orthanc_id,
            )
            .filter(
                Dataset.valid == True,
                Dataset_Patients.valid == True,
                Patient.valid == True,
            )
            .group_by(Dataset.id, Dataset.dataset_name, Patient.patient_sex)
            .all()
        )

        result = {}
        for dataset_id, dataset_name, sex, count in query:
            if sex == "M":
                result["Male"] = count
            elif sex == "F":
                result["Female"] = count

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dashboard.route("/dashboard_modality_count", methods=["GET"])
def get_all_datasets_modality_distribution():
    try:
        query = (
            db.session.query(
                func.unnest(Dataset.modalities).label("modality"),
                func.count().label("count"),
            )
            .filter(Dataset.valid == True)
            .group_by(func.unnest(Dataset.modalities))
            .all()
        )

        result = {}
        for modality, count in query:
            result[modality] = count

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dashboard.route("/dashboard_patient_age_distribution", methods=["GET"])
def get_patient_age_distribution():
    try:
        current_year = datetime.now().year

        query = (
            db.session.query(Patient.patient_birthdate)
            .filter(Patient.valid == True)
            .all()
        )

        age_groups = {}
        total_patients = 0

        for (birthdate,) in query:
            if birthdate and len(birthdate) == 8:  
                birth_year = int(birthdate[:4])
                age = current_year - birth_year
                group = math.floor(age / 10) * 10  
                age_groups[group] = age_groups.get(group, 0) + 1
                total_patients += 1

        age_distribution = {
            f"{group}-{group+9}": count for group, count in age_groups.items()
        }

        sorted_distribution = dict(
            sorted(age_distribution.items(), key=lambda x: int(x[0].split("-")[0]))
        )

        return jsonify(sorted_distribution)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@dashboard.route("/dashboard_dataset_study_description", methods=["GET"])
def get_dataset_study_description_distribution():
    try:
        dataset_id = request.args.get("dataset_id", type=int)

        query = (
            db.session.query(
                Study.study_description,
                func.count(Study.study_orthanc_id.distinct()).label("study_count"),
            )
            .join(
                Dataset_Studies,
                Dataset_Studies.study_orthanc_id == Study.study_orthanc_id,
            )
            .filter(
                Dataset_Studies.dataset_id == dataset_id,
                Dataset_Studies.valid == True,
                Study.valid == True,
            )
            .group_by(Study.study_description)
            .all()
        )

        result = {
            description if description else "Unknown": count
            for description, count in query
        }
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@dashboard.route("/dashboard_dataset_series_description", methods=["GET"])
def get_dataset_series_description_distribution():
    try:
        dataset_id = request.args.get("dataset_id", type=int)

        query = (
            db.session.query(
                Series.series_description,
                func.count(Series.series_orthanc_id.distinct()).label("series_count"),
            )
            .join(
                Dataset_Series,
                Dataset_Series.series_orthanc_id == Series.series_orthanc_id,
            )
            .filter(
                Dataset_Series.dataset_id == dataset_id,
                Dataset_Series.valid == True,
                Series.valid == True,
            )
            .group_by(Series.series_description)
            .all()
        )

        result = {
            description if description else "Unknown": count
            for description, count in query
        }
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@dashboard.route("/dashboard_dataset_gender_count", methods=["GET"])
def get_dataset_gender_distribution():
    dataset_id = request.args.get("dataset_id", type=int)
    try:
        query = (
            db.session.query(
                Dataset.id,
                Dataset.dataset_name,
                Patient.patient_sex,
                func.count(Patient.patient_orthanc_id.distinct()).label(
                    "patient_count"
                ),
            )
            .join(Dataset_Patients, Dataset.id == Dataset_Patients.dataset_id)
            .join(
                Patient,
                Dataset_Patients.patient_orthanc_id == Patient.patient_orthanc_id,
            )
            .filter(
                Dataset.id == dataset_id,
                Dataset.valid == True,
                Dataset_Patients.valid == True,
                Patient.valid == True,
            )
            .group_by(Dataset.id, Dataset.dataset_name, Patient.patient_sex)
            .all()
        )

        result = {"Male": 0, "Female": 0, "Unknown": 0}
        for _, _, sex, count in query:
            if sex == "M":
                result["Male"] = count
            elif sex == "F":
                result["Female"] = count
            else:
                result["Unknown"] = count

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# dashboard.route("/dashboard_patient_age_distribution", methods=["GET"])
# def get_dataset_age_distribution_pie():
#     dataset_id = request.args.get("dataset_id", type=int)
#     try:
#         current_year = datetime.now().year

#         query = (
#             db.session.query(Patient.patient_birthdate)
#             .join(
#                 Dataset_Patients,
#                 Dataset_Patients.patient_orthanc_id == Patient.patient_orthanc_id,
#             )
#             .filter(Dataset_Patients.dataset_id == dataset_id)
#             .filter(Dataset_Patients.valid == True, Patient.valid == True)
#             .all()
#         )

#         age_groups = {}
#         total_patients = 0

#         for (birthdate,) in query:
#             if birthdate and len(birthdate) == 8:
#                 birth_year = int(birthdate[:4])
#                 age = current_year - birth_year
#                 group = math.floor(age / 10) * 10
#                 age_groups[group] = age_groups.get(group, 0) + 1
#                 total_patients += 1

#         age_distribution = {
#             f"{group}-{group+9}": count for group, count in age_groups.items()
#         }

#         sorted_distribution = dict(
#             sorted(age_distribution.items(), key=lambda x: int(x[0].split("-")[0]))
#         )

#         return jsonify(sorted_distribution)

#     except Exception as e:
#         return jsonify({"error": str(e)}), 500


# ------------------------------------------ Bar Line Chart --------------------------------------
@dashboard.route("/dashboard_patient_growth", methods=["GET"])
def get_patient_growth():
    try:
        earliest_date = db.session.query(func.min(Patient.create_time)).scalar()
        latest_date = db.session.query(func.max(Patient.create_time)).scalar()

        if not earliest_date or not latest_date:
            return jsonify({"error": "No data available"}), 404

        query = (
            db.session.query(
                func.date_trunc("day", Patient.create_time).label("date"),
                func.count(Patient.patient_orthanc_id.distinct()).label("count"),
            )
            .filter(Patient.valid == True)
            .group_by(func.date_trunc("day", Patient.create_time))
            .order_by("date")
            .all()
        )

        dates = []
        counts = []
        cumulative_count = 0

        current_date = earliest_date.date()
        end_date = latest_date.date()

        for date, count in query:
            date = date.date()
            while current_date < date:
                dates.append(current_date.strftime("%Y-%m-%d"))
                counts.append(cumulative_count)
                current_date += timedelta(days=1)

            cumulative_count += count
            dates.append(date.strftime("%Y-%m-%d"))
            counts.append(cumulative_count)
            current_date = date + timedelta(days=1)

        while current_date <= end_date:
            dates.append(current_date.strftime("%Y-%m-%d"))
            counts.append(cumulative_count)
            current_date += timedelta(days=1)

        return jsonify({"dates": dates, "counts": counts})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
