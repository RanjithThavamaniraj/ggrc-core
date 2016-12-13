# Copyright (C) 2016 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Integration tests for WithSimilarityScore logic."""

import json

from ggrc import db
from ggrc.models import Assessment
from ggrc.models import Request
import ggrc.models as models
from ggrc.snapshotter.rules import Types


import integration.ggrc
import integration.ggrc.generator
from integration.ggrc.models import factories


# pylint: disable=super-on-old-class; TestCase is a new-style class
class TestWithSimilarityScore(integration.ggrc.TestCase):
  """Integration test suite for WithSimilarityScore functionality."""
  def setUp(self):
    super(TestWithSimilarityScore, self).setUp()
    self.obj_gen = integration.ggrc.generator.ObjectGenerator()

    self.client.get("/login")

  @staticmethod
  def make_relationships(source, destinations):
    for destination in destinations:
      factories.RelationshipFactory(
          source=source,
          destination=destination,
      )

  @staticmethod
  def get_object_snapshot(scope_parent, object_):
    # pylint: disable=protected-access
    return db.session.query(models.Snapshot).filter(
        models.Snapshot.parent_type == scope_parent._inflector.table_singular,
        models.Snapshot.parent_id == scope_parent.id,
        models.Snapshot.child_type == object_._inflector.table_singular,
        models.Snapshot.child_id == object_.id
    ).one()

  def make_scope_relationships(self, source, scope_parent, objects):
    """Create relationships between object and snapshots of provided object"""
    snapshots = []
    for object_ in objects:
      snapshot = self.get_object_snapshot(scope_parent, object_)
      snapshots += [snapshot]
    self.make_relationships(source, snapshots)

  def make_assessments(self, assessment_mappings):
    """Create six assessments and map them to audit, control, regulation.

    Each of the created assessments is mapped to its own subset of {audit,
    control, regulation} so each of them has different similarity weight.

    Returns: the six generated assessments and their weights in a dict.
    """

    assessments = [factories.AssessmentFactory()
                   for _ in range(len(assessment_mappings))]
    for assessment, all_mappings in zip(assessments, assessment_mappings):
      audit = [x for x in all_mappings if x.type == "Audit"][0]
      mappings = all_mappings[1:]
      ordinary_mappings = [x for x in mappings if x.type not in Types.all]
      snapshot_mappings = [x for x in mappings if x.type in Types.all]
      self.make_relationships(assessment, [audit] + ordinary_mappings)
      self.make_scope_relationships(assessment, audit,
                                    snapshot_mappings)

    return assessments

  def test_similarity_for_request(self):
    """Check special case for similarity for Request by Audit."""
    request1 = factories.RequestFactory(audit_id=self.audit.id)
    request2 = factories.RequestFactory(audit_id=self.audit.id)

    self.make_relationships(request1, [self.control, self.regulation])

    requests_by_request = Request.get_similar_objects_query(
        id_=request1.id,
        types=["Request"],
        threshold=0,
    ).all()

    self.assertSetEqual(
        {(obj.type, obj.id, obj.weight) for obj in requests_by_request},
        {("Request", request2.id, 5)},
    )

    requests_by_assessment = Assessment.get_similar_objects_query(
        id_=self.assessment.id,
        types=["Request"],
        threshold=0,
    ).all()

    self.assertSetEqual(
        {(obj.type, obj.id, obj.weight) for obj in requests_by_assessment},
        {("Request", request1.id, 18),
         ("Request", request2.id, 5)},
    )

    assessments_by_request = Request.get_similar_objects_query(
        id_=request1.id,
        types=["Assessment"],
        threshold=0,
    ).all()

    other_assessments = {
        ("Assessment", assessment.id, self.id_weight_map[assessment.id])
        for assessment in self.other_assessments
    }
    self.assertSetEqual(
        {(obj.type, obj.id, obj.weight) for obj in assessments_by_request},
        {("Assessment", self.assessment.id, 18)}.union(other_assessments),
    )

  def test_get_similar_basic(self):
    """Basic check of similar objects manually and via Query API.

    We create two programs, map them to the same control, create two audits
    and verify that we get the same result manually and via Query API.
    """
    program_1 = factories.ProgramFactory(title="Program 1")
    program_2 = factories.ProgramFactory(title="Program 2")

    control_program_1 = factories.ControlFactory(title="Control 1")

    self.make_relationships(
        program_1, [
            control_program_1,
        ],
    )

    self.make_relationships(
        program_2, [
            control_program_1,
        ],
    )

    program_1 = models.Program.query.filter_by(title="Program 1").one()
    program_2 = models.Program.query.filter_by(title="Program 2").one()
    control_program_1 = models.Control.query.filter_by(title="Control 1").one()

    _, audit_1 = self.obj_gen.generate_object(models.Audit, {
        "title": "Audit 1",
        "program": {"id": program_1.id},
        "status": "Planned"
    })

    _, audit_2 = self.obj_gen.generate_object(models.Audit, {
        "title": "Audit 2",
        "program": {"id": program_2.id},
        "status": "Planned"
    })

    assessment_mappings = [
        [audit_1, control_program_1],
        [audit_2, control_program_1],
    ]

    assessment_1, assessment_2 = self.make_assessments(assessment_mappings)

    similar_objects = models.Assessment.get_similar_objects_query(
        id_=assessment_1.id,
        types=["Assessment"],
    ).all()

    expected_ids = {assessment_2.id}

    self.assertSetEqual(
        {obj.id for obj in similar_objects},
        expected_ids,
    )

    query = [{
        "object_name": "Assessment",
        "type": "ids",
        "filters": {
            "expression": {
                "op": {"name": "similar"},
                "object_name": "Assessment",
                "ids": [str(assessment_1.id)],
            },
        },
    }]
    response = self.client.post(
        "/query",
        data=json.dumps(query),
        headers={"Content-Type": "application/json"},
    )
    self.assertSetEqual(
        set(json.loads(response.data)[0]["Assessment"]["ids"]),
        expected_ids,
    )

  def test_similar_partially_matching(self):
    """Basic check of similar objects manually and via Query API.

    We create three programs, map one them to the two regulations, create two
    audits and verify that we get the same result manually and via Query API.

    We also ensure that for only single matching regulation we do not
    fetch that assessment is as related.
    """

    # pylint: disable=too-many-locals

    program_1 = factories.ProgramFactory(title="Program 1")
    program_2 = factories.ProgramFactory(title="Program 2")
    program_3 = factories.ProgramFactory(title="Program 3")

    regulation_1_program_1 = factories.RegulationFactory(title="Regulation 1")
    regulation_2_program_1 = factories.RegulationFactory(title="Regulation 2")

    self.make_relationships(
        program_1, [
            regulation_1_program_1,
            regulation_2_program_1,
        ],
    )

    self.make_relationships(
        program_2, [
            regulation_1_program_1,
            regulation_2_program_1,
        ],
    )

    self.make_relationships(
        program_3, [
            regulation_1_program_1,
        ],
    )

    program_1 = models.Program.query.filter_by(title="Program 1").one()
    program_2 = models.Program.query.filter_by(title="Program 2").one()
    program_3 = models.Program.query.filter_by(title="Program 3").one()

    regulation_1_program_1 = models.Regulation.query.filter_by(
        title="Regulation 1").one()
    regulation_2_program_1 = models.Regulation.query.filter_by(
        title="Regulation 2").one()

    _, audit_1 = self.obj_gen.generate_object(models.Audit, {
        "title": "Audit 1",
        "program": {"id": program_1.id},
        "status": "Planned",
    })

    _, audit_2 = self.obj_gen.generate_object(models.Audit, {
        "title": "Audit 2",
        "program": {"id": program_2.id},
        "status": "Planned",
    })

    _, audit_3 = self.obj_gen.generate_object(models.Audit, {
        "title": "Audit 3",
        "program": {"id": program_3.id},
        "status": "Planned",
    })

    assessment_mappings = [
        [audit_1, regulation_1_program_1, regulation_2_program_1],
        [audit_2, regulation_1_program_1, regulation_2_program_1],
        [audit_3, regulation_1_program_1],
    ]

    assessment_1, assessment_2, assessment_3 = self.make_assessments(
        assessment_mappings)

    similar_objects = models.Assessment.get_similar_objects_query(
        id_=assessment_1.id,
        types=["Assessment"],
    ).all()

    expected_ids = {assessment_2.id}

    self.assertSetEqual(
        {obj.id for obj in similar_objects},
        expected_ids,
    )
    self.assertNotIn(assessment_3.id, similar_objects)

    query = [{
        "object_name": "Assessment",
        "type": "ids",
        "filters": {
            "expression": {
                "op": {"name": "similar"},
                "object_name": "Assessment",
                "ids": [str(assessment_1.id)],
            },
        },
    }]
    response = self.client.post(
        "/query",
        data=json.dumps(query),
        headers={"Content-Type": "application/json"},
    )
    self.assertSetEqual(
        set(json.loads(response.data)[0]["Assessment"]["ids"]),
        expected_ids,
    )

  def test_sort_by_similarity(self):
    """Check sorting by __similarity__ value with query API."""

    # pylint: disable=too-many-locals

    program_1 = factories.ProgramFactory(title="Program 1")

    regulation_1_program_1 = factories.RegulationFactory(title="Regulation 1")
    regulation_2_program_1 = factories.RegulationFactory(title="Regulation 2")
    control_1_program_1 = factories.ControlFactory(title="Control 1")
    control_2_program_1 = factories.ControlFactory(title="Control 2")

    self.make_relationships(
        program_1, [
            regulation_1_program_1,
            regulation_2_program_1,
            control_1_program_1,
            control_2_program_1
        ],
    )

    program_1 = models.Program.query.filter_by(title="Program 1").one()

    _, audit_1 = self.obj_gen.generate_object(models.Audit, {
        "title": "Audit 1",
        "program": {"id": program_1.id},
        "status": "Planned",
    })

    _, audit_2 = self.obj_gen.generate_object(models.Audit, {
        "title": "Audit 2",
        "program": {"id": program_1.id},
        "status": "Planned",
    })

    regulation_1_program_1 = models.Regulation.query.filter_by(
        title="Regulation 1").one()
    regulation_2_program_1 = models.Regulation.query.filter_by(
        title="Regulation 2").one()
    control_1_program_1 = models.Control.query.filter_by(
        title="Control 1").one()
    control_2_program_1 = models.Control.query.filter_by(
        title="Control 2").one()

    assessment_mappings = [
        [audit_1,
         regulation_1_program_1, regulation_2_program_1,
         control_1_program_1, control_2_program_1],
        [audit_1, control_1_program_1, control_2_program_1],
        [audit_1,
         regulation_1_program_1, control_1_program_1],
        [audit_2,
         regulation_1_program_1, regulation_2_program_1,
         control_1_program_1, control_2_program_1],
        [audit_2,
         regulation_1_program_1, control_1_program_1],
        [audit_2, control_1_program_1, control_2_program_1],
    ]

    weights = [
        [13, 18, 20, 25, 26],
        [10, 15, 20, 20, 25],
        [10, 13, 13, 15, 18],
        [13, 18, 20, 25, 26],
        [10, 13, 13, 15, 18],
        [10, 15, 20, 20, 25]
    ]

    assessments = self.make_assessments(
        assessment_mappings)
    assessment_ids = [ass.id for ass in assessments]

    for aid, weight_defs in zip(assessment_ids, weights):
      similar_objects = models.Assessment.get_similar_objects_query(
          id_=aid,
          types=["Assessment"],
      ).all()

      sorted_similar = sorted(similar_objects,
                              key=lambda x: x.weight)

      self.assertEqual(
          weight_defs,
          [x.weight for x in sorted_similar]
      )

      query = [{
          "object_name": "Assessment",
          "type": "ids",
          "order_by": [{"name": "__similarity__"}],
          "filters": {
              "expression": {
                  "op": {"name": "similar"},
                  "object_name": "Assessment",
                  "ids": [str(aid)],
              },
          },
      }]
      response = self.client.post(
          "/query",
          data=json.dumps(query),
          headers={"Content-Type": "application/json"},
      )

      # note that in our test data every similar object has a different weight;
      # the order of objects with same weight is undefined after sorting
      self.assertListEqual(
          json.loads(response.data)[0]["Assessment"]["ids"],
          [obj.id for obj in sorted_similar],
      )

  def test_empty_similar_results(self):
    """Check empty similarity result."""
    query = [{
        "object_name": "Assessment",
        "type": "ids",
        "filters": {
            "expression": {
                "op": {"name": "similar"},
                "object_name": "Assessment",
                "ids": ["-1"],
            },
        },
    }]
    response = self.client.post(
        "/query",
        data=json.dumps(query),
        headers={"Content-Type": "application/json"},
    )

    self.assertListEqual(
        response.json[0]["Assessment"]["ids"],
        [],
    )

  def test_invalid_sort_by_similarity(self):
    """Check sorting by __similarity__ with query API when it is impossible."""

    # no filter by similarity but order by similarity
    query = [{
        "object_name": "Assessment",
        "order_by": [{"name": "__similarity__"}],
        "filters": {"expression": {}},
    }]

    self.assert400(self.client.post(
        "/query",
        data=json.dumps(query),
        headers={"Content-Type": "application/json"},
    ))

    # filter by similarity in one query and order by similarity in another
    query = [
        {
            "object_name": "Assessment",
            "filters": {
                "expression": {
                    "op": {"name": "similar"},
                    "object_name": "Assessment",
                    "ids": [1],
                },
            },
        },
        {
            "object_name": "Assessment",
            "order_by": [{"name": "__similarity__"}],
            "filters": {"expression": {}},
        },
    ]

    self.assert400(self.client.post(
        "/query",
        data=json.dumps(query),
        headers={"Content-Type": "application/json"},
    ))
