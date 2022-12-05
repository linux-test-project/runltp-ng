pipeline {
  agent {
    node {
      label "runltp-ng"
    }
  }
  environment {
    TEST_QEMU_IMAGE    = "/data/image.qcow2"
    TEST_QEMU_PASSWORD = "root"
    TEST_SSH_USERNAME  = "auto"
    TEST_SSH_PASSWORD  = "auto1234"
    TEST_SSH_KEY_FILE  = "/data/jenkins_rsa"
  }
  stages {
    stage("Test host") {
      steps {
        catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
          sh 'pytest -n 8 -m "not qemu and not ssh" --junit-xml=results-host.xml'
        }
      }
    }
    stage("Test SSH") {
      steps {
        catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
          sh 'pytest -n 8 -m "ssh" --junit-xml=results-ssh.xml'
        }
      }
    }
    stage("Test Qemu") {
      steps {
        catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
          sh 'pytest -m "qemu" --junit-xml=results-qemu.xml'
        }
      }
    }
  }
  post {
    always {
      junit 'results-*.xml'
    }
  }
}